"""
Restablecimiento de contraseña autorizado con el segundo factor.

La persona demuestra que controla su segundo factor —código de la aplicación de
autenticación, código de respaldo o código enviado a su correo institucional— y con
eso autoriza el cambio. Nunca se envía un enlace que por sí solo cambie la
contraseña: un código de un solo uso deja menos superficie que un enlace con
permisos viajando por el correo.

Condiciones:
  * Solo funciona con cuentas que tengan algún segundo factor activo.
  * Los intentos fallidos usan el mismo contador de bloqueo que el ingreso normal.
  * Un código de respaldo se consume al usarlo, igual que al iniciar sesión.
  * El cambio queda en eventos_seguridad y en el log de auditoría.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src import config
from src.database.auditoria import registrar_evento_seguridad, registrar_log
from src.database.connection import consultar, ejecutar
from src.seguridad.contrasenas import hash_password, validar_politica
from src.seguridad.autenticacion import _codigo_valido, canal_mfa

MENSAJE_GENERICO = ("Si la cuenta existe y tiene la verificación en dos pasos activa, podrá "
                    "restablecer la contraseña con su código.")


@dataclass
class Resultado:
    ok: bool
    mensaje: str = ""
    usuario_id: int | None = None
    errores: list | None = None
    canal: str = ""          # "app", "correo" o "ambos"


def puede_restablecer(correo: str) -> Resultado:
    """Primer paso: comprueba que la cuenta admite este camino.
    El mensaje es el mismo exista o no la cuenta, para no revelar qué correos están registrados."""
    correo = (correo or "").strip().lower()
    u = consultar("SELECT id, activo, bloqueado_hasta FROM usuarios WHERE correo = %s",
                  (correo,), uno=True)
    if not u:
        registrar_evento_seguridad("RECUPERACION_SOLICITADA", correo, detalle="Correo no registrado")
        return Resultado(False, MENSAJE_GENERICO)
    if u["bloqueado_hasta"] and u["bloqueado_hasta"] > datetime.now():
        return Resultado(False, "La cuenta está bloqueada temporalmente. Intente más tarde.")
    canal = canal_mfa(u["id"]) if u["activo"] else ""
    if not canal:
        registrar_evento_seguridad("RECUPERACION_SOLICITADA", correo, u["id"],
                                   "Cuenta inactiva o sin segundo factor")
        return Resultado(False, MENSAJE_GENERICO)
    registrar_evento_seguridad("RECUPERACION_SOLICITADA", correo, u["id"], f"Cuenta apta ({canal})")
    return Resultado(True, usuario_id=u["id"], canal=canal)


def restablecer(usuario_id: int, codigo: str, nueva: str, repetir: str) -> Resultado:
    """Segundo paso: valida el código del segundo factor y aplica la contraseña nueva."""
    u = consultar("SELECT correo, intentos_fallidos, bloqueado_hasta, password_hash FROM usuarios "
                  "WHERE id = %s", (usuario_id,), uno=True)
    if not u:
        return Resultado(False, MENSAJE_GENERICO)
    ahora = datetime.now()
    if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora:
        return Resultado(False, "La cuenta está bloqueada temporalmente. Intente más tarde.")

    if nueva != repetir:
        return Resultado(False, "Las contraseñas no coinciden.")
    errores = validar_politica(nueva)
    if errores:
        return Resultado(False, "La contraseña no cumple la política.", errores=errores)

    # El código se valida al final para no gastar un código de respaldo por un error de tecleo
    if not _codigo_valido(usuario_id, codigo):
        intentos = u["intentos_fallidos"] + 1
        if intentos >= config.MAX_INTENTOS_LOGIN:
            ejecutar("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = %s WHERE id = %s",
                     (ahora + timedelta(minutes=config.MINUTOS_BLOQUEO), usuario_id))
            registrar_evento_seguridad("BLOQUEO", u["correo"], usuario_id,
                                       "Intentos fallidos al restablecer la contraseña")
            return Resultado(False, f"Cuenta bloqueada por {config.MINUTOS_BLOQUEO} minutos.")
        ejecutar("UPDATE usuarios SET intentos_fallidos = %s WHERE id = %s", (intentos, usuario_id))
        registrar_evento_seguridad("RECUPERACION_FALLIDA", u["correo"], usuario_id, "Código incorrecto")
        return Resultado(False, "El código no es correcto o ya fue utilizado.")

    from src.seguridad.contrasenas import verificar_password
    if verificar_password(nueva, u["password_hash"])[0]:
        return Resultado(False, "La nueva contraseña debe ser distinta de la anterior.")

    ejecutar("UPDATE usuarios SET password_hash = %s, debe_cambiar_password = 0, "
             "intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = %s",
             (hash_password(nueva), usuario_id))
    registrar_evento_seguridad("RECUPERACION_EXITOSA", u["correo"], usuario_id,
                               "Contraseña restablecida con el segundo factor")
    registrar_log(usuario_id, "RESTABLECER_PASSWORD", "usuarios", usuario_id,
                  "Restablecida por el propio usuario con el segundo factor")
    try:
        from src.servicios.avisos import password_cambiada
        password_cambiada(usuario_id, "el restablecimiento con el segundo factor")
    except Exception:                                     # noqa: BLE001
        # Bandit B110: la contrasena ya quedo restablecida; solo fallo el aviso,
        # pero el fallo del canal de correo debe quedar registrado.
        logging.getLogger(__name__).warning(
            "No se pudo avisar del restablecimiento al usuario %s", usuario_id, exc_info=True)
    return Resultado(True, "Contraseña actualizada. Ya puede iniciar sesión.")
