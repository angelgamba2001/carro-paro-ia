"""
Ajustes de seguridad editables por el administrador desde la interfaz.

El valor del .env es el de arranque; si el administrador lo cambia en
«Auditoría y seguridad → Configuración», queda en la tabla `configuracion` y se
aplica sin reiniciar (la web y la API lo releen cada pocos segundos). Cada cambio
queda en el log de auditoría con el valor anterior y el nuevo.
"""
import logging
import time

from src import config
from src.database.auditoria import registrar_log
from src.database.connection import consultar, ejecutar

log = logging.getLogger(__name__)

# clave -> (etiqueta, mínimo, máximo)
AJUSTES = {
    "MINUTOS_INACTIVIDAD": ("Expiración de la sesión web por inactividad (minutos)", 1, 480),
    "JWT_MINUTOS_EXPIRACION": ("Expiración del token de la API (minutos)", 1, 480),
}
_TTL = 10                       # segundos que se reutiliza la lectura de la tabla
_cache = {"t": 0.0, "v": {}}


def _leer() -> dict:
    if time.time() - _cache["t"] < _TTL:
        return _cache["v"]
    try:
        valores = {f["clave"]: f["valor"] for f in consultar("SELECT clave, valor FROM configuracion") or []}
    except Exception:                                          # noqa: BLE001  (tabla aún sin migrar)
        valores = {}
    _cache.update(t=time.time(), v=valores)
    return valores


def por_defecto(clave: str) -> int:
    return int(getattr(config, clave))


def valor(clave: str) -> int:
    """Valor vigente: el de la tabla si es válido; si no, el del .env."""
    _, minimo, maximo = AJUSTES[clave]
    try:
        n = int(_leer().get(clave))
        if minimo <= n <= maximo:
            return n
    except (TypeError, ValueError):
        pass
    return por_defecto(clave)


def minutos_inactividad() -> int:
    return valor("MINUTOS_INACTIVIDAD")


def minutos_jwt() -> int:
    return valor("JWT_MINUTOS_EXPIRACION")


def actualizar(usuario: dict, clave: str, nuevo) -> int:
    from src.seguridad.permisos import exigir_permiso
    from src.servicios.errores import ErrorNegocio
    exigir_permiso(usuario, "usuarios.gestionar")
    if clave not in AJUSTES:
        raise ErrorNegocio("Ajuste desconocido.")
    etiqueta, minimo, maximo = AJUSTES[clave]
    try:
        n = int(nuevo)
    except (TypeError, ValueError):
        raise ErrorNegocio(f"{etiqueta}: debe ser un número entero.") from None
    if not minimo <= n <= maximo:
        raise ErrorNegocio(f"{etiqueta}: debe estar entre {minimo} y {maximo}.")
    anterior = valor(clave)
    ejecutar("INSERT INTO configuracion (clave, valor, usuario_id) VALUES (%s, %s, %s) "
             "ON DUPLICATE KEY UPDATE valor = VALUES(valor), usuario_id = VALUES(usuario_id)",
             (clave, str(n), usuario["id"]))
    _cache["t"] = 0.0
    registrar_log(usuario["id"], "CAMBIO_CONFIGURACION", "configuracion", None, f"{clave}: {anterior} -> {n}")
    return n
