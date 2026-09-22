"""Compatibilidad con la v1. La lógica real vive en src/seguridad/."""
from src.seguridad.autenticacion import autenticar
from src.seguridad.contrasenas import hash_password  # noqa: F401


def verificar_credenciales(correo: str, password_plana: str):
    r = autenticar(correo, password_plana)
    return r.usuario if r.ok else None
