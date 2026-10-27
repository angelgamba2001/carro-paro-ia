"""
Sesiones web registradas en el servidor.

La sesión de Streamlit vive en memoria de cada pestaña; sin un registro del lado del
servidor, cerrar sesión en una pestaña no afecta a las otras y nada puede revocarse.
Aquí cada ingreso crea un token (tabla sesiones_activas) y cada petición comprueba que
siga vigente. Con eso:

  * cerrar sesión la invalida en el servidor, no solo en la pestaña;
  * con SESION_UNICA=1, entrar desde otro lugar cierra la sesión anterior y queda
    registrado (SESION_REEMPLAZADA);
  * cambiar o restablecer la contraseña, o desactivar la cuenta, cierra las sesiones.

Si la tabla aún no existe (falta ejecutar scripts/migrar_seguridad.py) el sistema sigue
funcionando como antes, sin revocación.
"""
import logging
import secrets

from src import config
from src.database.auditoria import registrar_evento_seguridad
from src.database.connection import consultar, ejecutar

log = logging.getLogger(__name__)
_lista = False


def disponible() -> bool:
    global _lista
    if not _lista:
        try:
            _lista = bool(consultar("SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() "
                                    "AND table_name = 'sesiones_activas'", uno=True))
        except Exception:                                             # noqa: BLE001
            return False
    return _lista


def crear(usuario: dict, origen: str = "WEB") -> str:
    """Registra una sesión nueva y devuelve su token ('' si no hay tabla)."""
    if not disponible():
        return ""
    token = secrets.token_hex(16)
    try:
        ejecutar("DELETE FROM sesiones_activas WHERE creada < DATE_SUB(NOW(), INTERVAL 1 DAY)")
        if config.SESION_UNICA:
            previas = consultar("SELECT COUNT(*) AS n FROM sesiones_activas WHERE usuario_id = %s",
                                (usuario["id"],), uno=True)
            if previas and int(previas["n"]):
                ejecutar("DELETE FROM sesiones_activas WHERE usuario_id = %s", (usuario["id"],))
                registrar_evento_seguridad("SESION_REEMPLAZADA", usuario.get("correo"), usuario["id"],
                                           "Un nuevo ingreso cerró la sesión anterior", origen)
        ejecutar("INSERT INTO sesiones_activas (token, usuario_id, origen) VALUES (%s,%s,%s)",
                 (token, usuario["id"], origen))
    except Exception:                                                 # noqa: BLE001
        log.error("No se pudo registrar la sesión del usuario %s", usuario.get("id"), exc_info=True)
        return ""
    return token


def vigente(token: str, usuario_id: int) -> bool:
    """¿Sigue abierta esta sesión? Sin token (tabla ausente o sesión antigua) se acepta."""
    if not token or not disponible():
        return True
    try:
        return bool(consultar("SELECT 1 FROM sesiones_activas WHERE token = %s AND usuario_id = %s",
                              (token, usuario_id), uno=True))
    except Exception:                                                 # noqa: BLE001
        return True


def cerrar(token: str):
    if token and disponible():
        ejecutar("DELETE FROM sesiones_activas WHERE token = %s", (token,))


def cerrar_todas(usuario_id: int, excepto: str = ""):
    """Cierra todas las sesiones de una persona, salvo (opcionalmente) la actual."""
    if not disponible():
        return
    try:
        ejecutar("DELETE FROM sesiones_activas WHERE usuario_id = %s AND token <> %s", (usuario_id, excepto or ""))
    except Exception:                                                 # noqa: BLE001
        log.error("No se pudieron cerrar las sesiones del usuario %s", usuario_id, exc_info=True)
