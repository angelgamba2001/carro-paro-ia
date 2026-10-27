"""
Autenticación con bloqueo por intentos fallidos (heredado de SGHCU: 5 intentos / 15 min).
Mensajes genéricos hacia el usuario; el detalle queda en eventos_seguridad.
"""
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src import config
from src.database.auditoria import registrar_evento_seguridad
from src.database.connection import consultar, ejecutar
from src.seguridad import correos
from src.seguridad.permisos import roles_adicionales
from src.seguridad.contrasenas import hash_password, validar_politica, verificar_password

MENSAJE_GENERICO = "Correo o contraseña incorrectos."

log = logging.getLogger(__name__)


def avisar_bloqueo(usuario_id: int, motivo: str):
    """El aviso por correo nunca puede tumbar el inicio de sesión."""
    try:
        from src.servicios.avisos import cuenta_bloqueada
        cuenta_bloqueada(usuario_id, motivo)
    except Exception:                                     # noqa: BLE001
        # Bandit B110: descartar la excepcion dejaba sin rastro un fallo del canal
        # de correo. El aviso sigue siendo accesorio y no interrumpe el ingreso.
        log.warning("No se pudo avisar del bloqueo al usuario %s", usuario_id, exc_info=True)

_CAMPOS_BASE = ("id, nombre, correo, rol, activo, password_hash, intentos_fallidos, "
                "bloqueado_hasta, debe_cambiar_password")
_modulos_listos = False


def hay_columna_modulos() -> bool:
    """¿Ya se aplicó scripts/migrar_visitante.py? Solo se recuerda el sí: mientras
    falte, se vuelve a preguntar, y así basta ejecutar la migración sin reiniciar."""
    global _modulos_listos
    if not _modulos_listos:
        _modulos_listos = bool(consultar(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() "
            "AND table_name = 'usuarios' AND column_name = 'modulos'", uno=True))
    return _modulos_listos


_tablas_listas: set = set()


def hay_tabla(nombre: str) -> bool:
    """¿Existe la tabla? Solo se recuerda el sí, igual que hay_columna_modulos."""
    if nombre not in _tablas_listas and consultar(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
            (nombre,), uno=True):
        _tablas_listas.add(nombre)
    return nombre in _tablas_listas


def _campos() -> str:
    """Columnas que se leen del usuario. `modulos` entra solo cuando la migración ya la
    creó: una base sin migrar sigue dejando entrar en vez de fallar con «Unknown column».
    Son siempre literales fijos de este módulo, nunca texto que escriba el usuario."""
    return _CAMPOS_BASE + (", modulos" if hay_columna_modulos() else "")


@dataclass
class ResultadoLogin:
    ok: bool
    usuario: dict | None = None
    mensaje: str = ""
    intentos_restantes: int | None = None
    requiere_mfa: bool = False      # contraseña correcta, falta el código de 6 dígitos
    canal_mfa: str = ""             # "app", "correo" o "ambos": de dónde saca el código


def _publico(u: dict) -> dict:
    """Datos del usuario que pueden viajar en sesión/token (sin hash)."""
    publico = {k: u[k] for k in ("id", "nombre", "correo", "rol", "activo", "debe_cambiar_password")}
    publico["modulos"] = u.get("modulos")      # solo lo usan las cuentas VISITANTE
    publico["roles_extra"] = roles_adicionales(u["id"])      # roles adicionales (tabla usuario_rol)
    return publico


def autenticar(correo: str, password: str, origen: str = "WEB") -> ResultadoLogin:
    correo = (correo or "").strip().lower()
    if not correo or not password:
        return ResultadoLogin(False, mensaje=MENSAJE_GENERICO)
    # El campo de usuario solo admite los caracteres de un correo. Se rechaza ANTES de
    # tocar la base de datos, y en el registro de seguridad NO se guarda lo escrito:
    # es justo el texto que alguien armó para probar el sistema.
    if not correos.login_valido(correo):
        registrar_evento_seguridad("LOGIN_FALLIDO", None, detalle="Caracteres no permitidos en el usuario",
                                   origen=origen)
        return ResultadoLogin(False, mensaje=correos.MENSAJE_LOGIN_CARACTERES)

    # Falso positivo B608: lo interpolado es la constante _CAMPOS (lista fija de columnas).
    # El dato del usuario viaja parametrizado en %s, no concatenado.
    u = consultar(f"SELECT {_campos()} FROM usuarios WHERE correo = %s",  # nosec B608
                  (correo,), uno=True)
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
            avisar_bloqueo(u["id"], "intentos de ingreso con contraseña incorrecta")
            return ResultadoLogin(False, mensaje=f"Cuenta bloqueada por {config.MINUTOS_BLOQUEO} minutos "
                                                 "por intentos fallidos.")
        ejecutar("UPDATE usuarios SET intentos_fallidos = %s WHERE id = %s", (intentos, u["id"]))
        registrar_evento_seguridad("LOGIN_FALLIDO", correo, u["id"], "Contraseña incorrecta", origen)
        return ResultadoLogin(False, mensaje=MENSAJE_GENERICO,
                              intentos_restantes=config.MAX_INTENTOS_LOGIN - intentos)

    if requiere_rehash:  # migración transparente SHA-256 (v1) -> bcrypt
        ejecutar("UPDATE usuarios SET password_hash = %s WHERE id = %s", (hash_password(password), u["id"]))
    ejecutar("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = %s", (u["id"],))

    canal = canal_mfa(u["id"])
    if canal:
        registrar_evento_seguridad("LOGIN_PASSWORD_OK", correo, u["id"], "Falta el segundo factor", origen)
        aviso = {"app": "Ingrese el código de su aplicación de autenticación.",
                 "correo": "Le enviamos un código a su correo institucional.",
                 "ambos": "Ingrese el código de su aplicación, o pida uno por correo."}[canal]
        return ResultadoLogin(False, usuario=_publico(u), requiere_mfa=True,
                              canal_mfa=canal, mensaje=aviso)

    ejecutar("UPDATE usuarios SET ultimo_acceso = NOW(), ultimo_acceso_origen = %s WHERE id = %s",
             (origen, u["id"]))
    registrar_evento_seguridad("LOGIN_OK", correo, u["id"], origen=origen)
    return ResultadoLogin(True, usuario=_publico(u))


def canal_mfa(usuario_id: int) -> str:
    """Por dónde puede recibir el código esta cuenta: app, correo, ambos o ninguno."""
    from src.seguridad.mfa import estado_mfa
    from src.seguridad.mfa_correo import disponible
    app = estado_mfa(usuario_id)["activo"]
    correo = disponible(usuario_id)
    if app and correo:
        return "ambos"
    if app:
        return "app"
    return "correo" if correo else ""


def _codigo_valido(usuario_id: int, codigo: str) -> bool:
    """Acepta el código venga del canal que venga: app, respaldo o correo."""
    from src.seguridad.mfa import verificar_segundo_factor
    from src.seguridad.mfa_correo import disponible, verificar as verificar_correo
    if verificar_segundo_factor(usuario_id, codigo):
        return True
    return disponible(usuario_id) and verificar_correo(usuario_id, codigo)


def completar_login_mfa(usuario_id: int, codigo: str, origen: str = "WEB") -> ResultadoLogin:
    """Segundo paso del ingreso: valida el código, sea de la aplicación de
    autenticación, de respaldo o el enviado al correo.
    Los intentos fallidos cuentan para el mismo bloqueo que la contraseña."""
    # Falso positivo B608: igual que arriba, _CAMPOS es una constante del modulo.
    u = consultar(f"SELECT {_campos()} FROM usuarios WHERE id = %s",  # nosec B608
                  (usuario_id,), uno=True)
    if not u or not u["activo"]:
        return ResultadoLogin(False, mensaje=MENSAJE_GENERICO)
    ahora = datetime.now()
    if u["bloqueado_hasta"] and u["bloqueado_hasta"] > ahora:
        return ResultadoLogin(False, mensaje="Cuenta bloqueada temporalmente.")

    if not _codigo_valido(usuario_id, codigo):
        intentos = u["intentos_fallidos"] + 1
        if intentos >= config.MAX_INTENTOS_LOGIN:
            ejecutar("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = %s WHERE id = %s",
                     (ahora + timedelta(minutes=config.MINUTOS_BLOQUEO), usuario_id))
            registrar_evento_seguridad("BLOQUEO", u["correo"], usuario_id,
                                       "Intentos fallidos del segundo factor", origen)
            avisar_bloqueo(usuario_id, "intentos fallidos del segundo factor")
            return ResultadoLogin(False, mensaje=f"Cuenta bloqueada por {config.MINUTOS_BLOQUEO} minutos.")
        ejecutar("UPDATE usuarios SET intentos_fallidos = %s WHERE id = %s", (intentos, usuario_id))
        registrar_evento_seguridad("MFA_FALLIDO", u["correo"], usuario_id, origen=origen)
        return ResultadoLogin(False, mensaje="Código incorrecto o ya utilizado.",
                              intentos_restantes=config.MAX_INTENTOS_LOGIN - intentos,
                              requiere_mfa=True, canal_mfa=canal_mfa(usuario_id))

    ejecutar("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL, ultimo_acceso = NOW(), "
             "ultimo_acceso_origen = %s WHERE id = %s", (origen, usuario_id))
    registrar_evento_seguridad("LOGIN_OK", u["correo"], usuario_id, "Con segundo factor", origen)
    return ResultadoLogin(True, usuario=_publico(u))


def revalidar_usuario(usuario_id: int) -> dict | None:
    """Defensa en profundidad: relee rol/estado desde la BD en cada solicitud.
    Si un admin desactiva o cambia el rol, la sesión abierta pierde los privilegios de inmediato."""
    # Falso positivo B608: igual que arriba, _CAMPOS es una constante del modulo.
    u = consultar(f"SELECT {_campos()} FROM usuarios WHERE id = %s",  # nosec B608
                  (usuario_id,), uno=True)
    if not u or not u["activo"]:
        return None
    return _publico(u)


def cambiar_password(usuario_id: int, actual: str, nueva: str, sesion_actual: str = "") -> list[str]:
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
    from src.seguridad import sesiones
    sesiones.cerrar_todas(usuario_id, sesion_actual)       # las demás sesiones abiertas dejan de valer
    try:
        from src.servicios.avisos import password_cambiada
        password_cambiada(usuario_id, "el cambio desde su perfil")
    except Exception:                                     # noqa: BLE001
        # Bandit B110: el cambio de contrasena ya esta hecho; solo fallo el aviso,
        # pero debe quedar registrado para poder auditarlo.
        log.warning("No se pudo avisar del cambio de contrasena al usuario %s",
                    usuario_id, exc_info=True)
    return []
