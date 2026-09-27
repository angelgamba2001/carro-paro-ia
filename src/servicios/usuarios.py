import pandas as pd

from src.database.auditoria import registrar_evento_seguridad, registrar_log
from src.database.connection import consultar, consultar_df, ejecutar
from src.seguridad.contrasenas import hash_password, validar_politica
from src.seguridad.permisos import ROLES, exigir_permiso, tiene_permiso
from src.servicios.errores import ErrorNegocio


def listar_usuarios(usuario: dict) -> pd.DataFrame:
    if not tiene_permiso(usuario, "usuarios.desbloquear"):
        exigir_permiso(usuario, "usuarios.gestionar")
    return consultar_df("""SELECT id, nombre, correo, rol, activo, intentos_fallidos, bloqueado_hasta,
                                  ultimo_acceso, debe_cambiar_password FROM usuarios ORDER BY nombre""")


def crear_usuario(usuario: dict, nombre: str, correo: str, password: str, rol: str) -> int:
    exigir_permiso(usuario, "usuarios.gestionar")
    from src.seguridad.correos import validar as validar_correo
    if not nombre.strip():
        raise ErrorNegocio("El nombre es obligatorio.")
    try:
        correo = validar_correo(correo)
    except ValueError as e:
        raise ErrorNegocio(str(e)) from e
    if rol not in ROLES:
        raise ErrorNegocio("Rol inválido.")
    errores = validar_politica(password)
    if errores:
        raise ErrorNegocio(" ".join(errores))
    if consultar("SELECT id FROM usuarios WHERE correo = %s", (correo,), uno=True):
        raise ErrorNegocio("Ya existe un usuario con ese correo.")
    nuevo = ejecutar("INSERT INTO usuarios (nombre, correo, password_hash, rol, debe_cambiar_password) "
                     "VALUES (%s,%s,%s,%s,1)", (nombre.strip(), correo, hash_password(password), rol))
    registrar_log(usuario["id"], "CREACION_USUARIO", "usuarios", nuevo, f"{correo} con rol {rol}")
    try:
        from src.servicios.avisos import cuenta_creada
        cuenta_creada(nuevo, usuario.get("nombre", ""))
    except Exception:                                     # noqa: BLE001
        pass
    return nuevo


def cambiar_rol(usuario: dict, usuario_id: int, rol: str):
    exigir_permiso(usuario, "usuarios.gestionar")
    if rol not in ROLES:
        raise ErrorNegocio("Rol inválido.")
    if usuario_id == usuario["id"]:
        raise ErrorNegocio("No puede cambiar su propio rol.")
    ejecutar("UPDATE usuarios SET rol = %s WHERE id = %s", (rol, usuario_id))
    registrar_log(usuario["id"], "CAMBIO_ROL", "usuarios", usuario_id, f"Nuevo rol: {rol}")


def cambiar_estado(usuario: dict, usuario_id: int, activo: bool):
    exigir_permiso(usuario, "usuarios.gestionar")
    if usuario_id == usuario["id"]:
        raise ErrorNegocio("No puede desactivar su propia cuenta.")
    ejecutar("UPDATE usuarios SET activo = %s WHERE id = %s", (1 if activo else 0, usuario_id))
    registrar_log(usuario["id"], "ACTUALIZACION", "usuarios", usuario_id,
                  "Activado" if activo else "Desactivado")


def desbloquear(usuario: dict, usuario_id: int):
    exigir_permiso(usuario, "usuarios.desbloquear")
    ejecutar("UPDATE usuarios SET bloqueado_hasta = NULL, intentos_fallidos = 0 WHERE id = %s", (usuario_id,))
    registrar_evento_seguridad("DESBLOQUEO", usuario_id=usuario_id, detalle=f"Por usuario {usuario['id']}")
    registrar_log(usuario["id"], "DESBLOQUEO", "usuarios", usuario_id)


def restablecer_password(usuario: dict, usuario_id: int, temporal: str):
    exigir_permiso(usuario, "usuarios.gestionar")
    errores = validar_politica(temporal)
    if errores:
        raise ErrorNegocio(" ".join(errores))
    ejecutar("UPDATE usuarios SET password_hash = %s, debe_cambiar_password = 1 WHERE id = %s",
             (hash_password(temporal), usuario_id))
    registrar_log(usuario["id"], "RESTABLECER_PASSWORD", "usuarios", usuario_id)


def log_auditoria(usuario: dict, dias: int = 30) -> pd.DataFrame:
    exigir_permiso(usuario, "auditoria.ver")
    return consultar_df("""SELECT a.fecha, u.nombre AS usuario, u.rol, a.accion, a.entidad, a.entidad_id,
                                  a.origen, a.detalle
                           FROM log_auditoria a LEFT JOIN usuarios u ON u.id = a.usuario_id
                           WHERE a.fecha >= DATE_SUB(NOW(), INTERVAL %s DAY)
                           ORDER BY a.fecha DESC""", (dias,))


def eventos_seguridad(usuario: dict, dias: int = 30) -> pd.DataFrame:
    exigir_permiso(usuario, "seguridad.ver")
    return consultar_df("""SELECT fecha, tipo, correo, origen, detalle FROM eventos_seguridad
                           WHERE fecha >= DATE_SUB(NOW(), INTERVAL %s DAY) ORDER BY fecha DESC""", (dias,))
