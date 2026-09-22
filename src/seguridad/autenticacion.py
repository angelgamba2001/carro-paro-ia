"""
Autenticación con bloqueo por intentos fallidos (heredado de SGHCU: 5 intentos / 15 min).
Mensajes genéricos hacia el usuario; el detalle queda en eventos_seguridad.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from src import config
from src.database.auditoria import registrar_evento_seguridad
from src.database.connection import consultar, ejecutar
from src.seguridad.contrasenas import hash_password, validar_politica, verificar_password

MENSAJE_GENERICO = "Correo o contraseña incorrectos."

_CAMPOS = ("id, nombre, correo, rol, activo, password_hash, intentos_fallidos, "
           "bloqueado_hasta, debe_cambiar_password")


@dataclass
class ResultadoLogin:
    ok: bool
    usuario: dict | None = None
    mensaje: str = ""
    intentos_restantes: int | None = None


def _publico(u: dict) -> dict:
    """Datos del usuario que pueden viajar en sesión/token (sin hash)."""
    return {k: u[k] for k in ("id", "nombre", "correo", "rol", "activo", "debe_cambiar_password")}


def autenticar(correo: str, password: str, origen: str = "WEB") -> ResultadoLogin:
    correo = (correo or "").strip().lower()
    if not correo or not password:
        return ResultadoLogin(False, mensaje=MENSAJE_GENERICO)

    u = consultar(f"SELECT {_CAMPOS} FROM usuarios WHERE correo = %s", (correo,), uno=True)
    if not u:
        registrar_evento_seguridad("LOGIN_FALLIDO", correo, detalle="Usuario inexistente", origen=origen)
        return ResultadoLogin(False, mensaje=MENSAJE_GENERICO)

    ahora = datetime.now()
    if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora:
        minutos = int((u["bloqueado_hasta"] - ahora).total_seconds() // 60) + 1
        registrar_evento_seguridad("LOGIN_FALLIDO", correo, u["id"], "Intento con cuenta bloqueada", origen)
        return ResultadoLogin(False, mensaje=f"Cuenta bloqueada temporalmente. Intente en {minutos} min.")

    if not u["activo"]:
        registrar_evento_seguridad("LOGIN_FALLIDO", correo, u["id"], "Usuario inactivo", origen)
        return ResultadoLogin(False, mensaje=MENSAJE_GENERICO)

    valida, requiere_rehash = verificar_password(password, u["password_hash"])
    if not valida:
        intentos = u["intentos_fallidos"] + 1
        if intentos >= config.MAX_INTENTOS_LOGIN:
            hasta = ahora + timedelta(minutes=config.MINUTOS_BLOQUEO)
            ejecutar("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = %s WHERE id = %s",
                     (hasta, u["id"]))
            registrar_evento_seguridad("BLOQUEO", correo, u["id"],
                                       f"{intentos} intentos fallidos; bloqueado {config.MINUTOS_BLOQUEO} min", origen)
            return ResultadoLogin(False, mensaje=f"Cuenta bloqueada por {config.MINUTOS_BLOQUEO} minutos "
                                                 "por intentos fallidos.")
        ejecutar("UPDATE usuarios SET intentos_fallidos = %s WHERE id = %s", (intentos, u["id"]))
        registrar_evento_seguridad("LOGIN_FALLIDO", correo, u["id"], "Contraseña incorrecta", origen)
        return ResultadoLogin(False, mensaje=MENSAJE_GENERICO,
                              intentos_restantes=config.MAX_INTENTOS_LOGIN - intentos)

    if requiere_rehash:  # migración transparente SHA-256 (v1) -> bcrypt
        ejecutar("UPDATE usuarios SET password_hash = %s WHERE id = %s", (hash_password(password), u["id"]))
    ejecutar("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_acceso = NOW() "
             "WHERE id = %s", (u["id"],))
    registrar_evento_seguridad("LOGIN_OK", correo, u["id"], origen=origen)
    return ResultadoLogin(True, usuario=_publico(u))


def revalidar_usuario(usuario_id: int) -> dict | None:
    """Defensa en profundidad: relee rol/estado desde la BD en cada solicitud.
    Si un admin desactiva o cambia el rol, la sesión abierta pierde los privilegios de inmediato."""
    u = consultar(f"SELECT {_CAMPOS} FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u or not u["activo"]:
        return None
    return _publico(u)


def cambiar_password(usuario_id: int, actual: str, nueva: str) -> list[str]:
    u = consultar("SELECT correo, password_hash FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u or not verificar_password(actual, u["password_hash"])[0]:
        return ["La contraseña actual no es correcta."]
    if actual == nueva:
        return ["La nueva contraseña debe ser distinta de la actual."]
    errores = validar_politica(nueva)
    if errores:
        return errores
    ejecutar("UPDATE usuarios SET password_hash = %s, debe_cambiar_password = 0 WHERE id = %s",
             (hash_password(nueva), usuario_id))
    registrar_evento_seguridad("CAMBIO_PASSWORD", u["correo"], usuario_id)
    return []
