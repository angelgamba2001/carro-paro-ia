"""
Roles personalizados y roles adicionales por persona.

* Un rol personalizado es un conjunto de permisos con nombre propio, creado desde la
  interfaz. Se guarda en las tablas roles / rol_permiso; su código lleva el prefijo R_.
* Una persona tiene un rol principal (usuarios.rol) y puede tener roles adicionales
  (usuario_rol). Sus permisos son la unión de todos.

Para que gestionar roles no sea una vía de escalada de privilegios, quien concede
permisos solo puede conceder los que él mismo tiene (el administrador los tiene todos).
Todo cambio queda en el log de auditoría con el valor anterior y el nuevo.
"""
import re
import unicodedata

from src.database.auditoria import registrar_log
from src.database.connection import consultar, ejecutar
from src.seguridad.permisos import (PERMISOS, PREFIJO_ROL, ROLES, ROLES_BASE, exigir_permiso,
                                    invalidar_cache, permisos_de, permisos_de_usuario)
from src.servicios.errores import ErrorNegocio

_NOMBRE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9 ._\-]{3,60}")


def _codigo(nombre: str) -> str:
    ascii_ = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    limpio = re.sub(r"[^A-Za-z0-9]+", "_", ascii_).strip("_").upper()
    return (PREFIJO_ROL + limpio)[:30]


def _exigir_alcance(usuario: dict, permisos: set):
    """Nadie concede lo que no tiene."""
    de_mas = permisos - permisos_de_usuario(usuario)
    if de_mas:
        raise ErrorNegocio("No puede conceder permisos que usted no tiene: " + ", ".join(sorted(de_mas)))


def _validar_permisos(permisos) -> set:
    elegidos = set(permisos or [])
    if not elegidos:
        raise ErrorNegocio("Elija al menos un permiso para el rol.")
    desconocidos = elegidos - set(PERMISOS)
    if desconocidos:
        raise ErrorNegocio("Permiso desconocido: " + ", ".join(sorted(desconocidos)))
    return elegidos


def listar_roles_personalizados(usuario: dict) -> list[dict]:
    exigir_permiso(usuario, "usuarios.gestionar")
    filas = consultar("SELECT codigo, nombre, descripcion FROM roles WHERE codigo LIKE %s ORDER BY nombre",
                      (PREFIJO_ROL + "%",)) or []
    salida = []
    for f in filas:
        usuarios = consultar("SELECT (SELECT COUNT(*) FROM usuarios WHERE rol = %s) + "
                             "(SELECT COUNT(*) FROM usuario_rol WHERE rol = %s) AS n",
                             (f["codigo"], f["codigo"]), uno=True)
        salida.append({**f, "permisos": sorted(permisos_de(f["codigo"])), "usuarios": int(usuarios["n"])})
    return salida


def crear_rol(usuario: dict, nombre: str, descripcion: str, permisos) -> str:
    exigir_permiso(usuario, "usuarios.gestionar")
    nombre = " ".join((nombre or "").split())
    if not _NOMBRE.fullmatch(nombre):
        raise ErrorNegocio("El nombre debe tener entre 3 y 60 caracteres: letras, números, espacios y . _ -")
    descripcion = " ".join((descripcion or "").split())[:255]
    elegidos = _validar_permisos(permisos)
    _exigir_alcance(usuario, elegidos)
    codigo = _codigo(nombre)
    if len(codigo) <= len(PREFIJO_ROL):
        raise ErrorNegocio("El nombre del rol no es válido.")
    if codigo in ROLES or consultar("SELECT 1 FROM roles WHERE codigo = %s", (codigo,), uno=True) \
            or consultar("SELECT 1 FROM roles WHERE LOWER(nombre) = LOWER(%s)", (nombre,), uno=True) \
            or nombre.lower() in {v[0].lower() for v in ROLES_BASE.values()}:
        raise ErrorNegocio("Ya existe un rol con ese nombre.")
    ejecutar("INSERT INTO roles (codigo, nombre, descripcion) VALUES (%s,%s,%s)",
             (codigo, nombre, descripcion or "Rol personalizado"))
    for p in sorted(elegidos):
        ejecutar("INSERT INTO rol_permiso (rol, permiso) VALUES (%s,%s)", (codigo, p))
    invalidar_cache()
    registrar_log(usuario["id"], "CREACION_ROL", "roles", None,
                  f"{codigo} con permisos: {', '.join(sorted(elegidos))}")
    return codigo


def cambiar_permisos_rol(usuario: dict, codigo: str, permisos):
    exigir_permiso(usuario, "usuarios.gestionar")
    if codigo in ROLES_BASE or not codigo.startswith(PREFIJO_ROL) or codigo not in ROLES:
        raise ErrorNegocio("Solo se pueden modificar los roles personalizados.")
    nuevos = _validar_permisos(permisos)
    anteriores = permisos_de(codigo)
    _exigir_alcance(usuario, nuevos - anteriores)          # lo que ya tenía el rol no se vuelve a exigir
    ejecutar("DELETE FROM rol_permiso WHERE rol = %s", (codigo,))
    for p in sorted(nuevos):
        ejecutar("INSERT INTO rol_permiso (rol, permiso) VALUES (%s,%s)", (codigo, p))
    invalidar_cache()
    registrar_log(usuario["id"], "CAMBIO_PERMISOS_ROL", "roles", None,
                  f"{codigo}: antes [{', '.join(sorted(anteriores))}] -> ahora [{', '.join(sorted(nuevos))}]")


def eliminar_rol(usuario: dict, codigo: str):
    exigir_permiso(usuario, "usuarios.gestionar")
    if codigo in ROLES_BASE or not codigo.startswith(PREFIJO_ROL) or codigo not in ROLES:
        raise ErrorNegocio("Solo se pueden eliminar los roles personalizados.")
    en_uso = consultar("SELECT (SELECT COUNT(*) FROM usuarios WHERE rol = %s) + "
                       "(SELECT COUNT(*) FROM usuario_rol WHERE rol = %s) AS n", (codigo, codigo), uno=True)
    if en_uso and int(en_uso["n"]):
        raise ErrorNegocio(f"El rol está asignado a {int(en_uso['n'])} persona(s). Reasígnelas antes de eliminarlo.")
    ejecutar("DELETE FROM roles WHERE codigo = %s", (codigo,))
    invalidar_cache()
    registrar_log(usuario["id"], "ELIMINACION_ROL", "roles", None, codigo)


def cambiar_roles_adicionales(usuario: dict, usuario_id: int, roles: list):
    """Reemplaza el conjunto de roles adicionales de una persona."""
    exigir_permiso(usuario, "usuarios.gestionar")
    if usuario_id == usuario["id"]:
        raise ErrorNegocio("No puede cambiar sus propios roles.")
    destino = consultar("SELECT rol FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not destino:
        raise ErrorNegocio("La cuenta no existe.")
    if destino["rol"] == "VISITANTE":
        raise ErrorNegocio("Una cuenta Visitante no admite roles adicionales: se le abren módulos.")
    elegidos = list(dict.fromkeys(roles or []))
    for r in elegidos:
        if r not in ROLES:
            raise ErrorNegocio(f"Rol inválido: {r}")
        if r == "VISITANTE":
            raise ErrorNegocio("El rol Visitante no puede ser adicional.")
        if r == destino["rol"]:
            raise ErrorNegocio("Ese rol ya es el principal de la cuenta.")
    anteriores = [f["rol"] for f in consultar("SELECT rol FROM usuario_rol WHERE usuario_id = %s ORDER BY rol",
                                              (usuario_id,)) or []]
    for r in set(elegidos) - set(anteriores):                # solo se valida lo que se agrega
        _exigir_alcance(usuario, permisos_de(r))
    ejecutar("DELETE FROM usuario_rol WHERE usuario_id = %s", (usuario_id,))
    for r in elegidos:
        ejecutar("INSERT INTO usuario_rol (usuario_id, rol) VALUES (%s,%s)", (usuario_id, r))
    registrar_log(usuario["id"], "CAMBIO_ROLES_ADICIONALES", "usuarios", usuario_id,
                  f"antes [{', '.join(anteriores) or '-'}] -> ahora [{', '.join(sorted(elegidos)) or '-'}]")


def cambiar_permisos_individuales(usuario: dict, usuario_id: int, permisos: list):
    """Reemplaza los permisos asignados directamente a una persona (se suman a los de sus roles).
    Permite que dos personas con el mismo rol tengan permisos distintos."""
    exigir_permiso(usuario, "usuarios.gestionar")
    if usuario_id == usuario["id"]:
        raise ErrorNegocio("No puede cambiar sus propios permisos.")
    destino = consultar("SELECT rol FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not destino:
        raise ErrorNegocio("La cuenta no existe.")
    if destino["rol"] == "VISITANTE":
        raise ErrorNegocio("Una cuenta Visitante no admite permisos individuales: se le abren módulos.")
    elegidos = list(dict.fromkeys(permisos or []))
    desconocidos = [p for p in elegidos if p not in PERMISOS]
    if desconocidos:
        raise ErrorNegocio("Permiso desconocido: " + ", ".join(sorted(desconocidos)))
    anteriores = [f["permiso"] for f in consultar(
        "SELECT permiso FROM usuario_permiso WHERE usuario_id = %s ORDER BY permiso", (usuario_id,)) or []]
    _exigir_alcance(usuario, set(elegidos) - set(anteriores))   # solo se valida lo que se agrega
    ejecutar("DELETE FROM usuario_permiso WHERE usuario_id = %s", (usuario_id,))
    for p in elegidos:
        ejecutar("INSERT INTO usuario_permiso (usuario_id, permiso) VALUES (%s,%s)", (usuario_id, p))
    registrar_log(usuario["id"], "CAMBIO_PERMISOS_USUARIO", "usuarios", usuario_id,
                  f"antes [{', '.join(anteriores) or '-'}] -> ahora [{', '.join(sorted(elegidos)) or '-'}]")


def permisos_efectivos(usuario_id: int) -> set:
    """Permisos de una persona (útil para mostrar y para pruebas)."""
    from src.seguridad.permisos import permisos_individuales, roles_adicionales
    u = consultar("SELECT rol FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u:
        return set()
    return permisos_de_usuario({"rol": u["rol"], "activo": 1, "roles_extra": roles_adicionales(usuario_id),
                                "permisos_extra": permisos_individuales(usuario_id)})

