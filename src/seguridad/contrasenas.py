"""Hash y política de contraseñas (A02 / A07 OWASP)."""
import hashlib
import re

import bcrypt

LONGITUD_MINIMA = 10


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def es_hash_bcrypt(valor: str) -> bool:
    return bool(valor) and valor.startswith(("$2a$", "$2b$", "$2y$"))


def verificar_password(password: str, hash_guardado: str) -> tuple[bool, bool]:
    """
    Retorna (valida, requiere_rehash).
    Acepta hashes SHA-256 de la v1 SOLO para migrarlos a bcrypt en el primer login.
    Ya no se acepta la contraseña en texto plano (la v1 lo permitía).
    """
    if not hash_guardado:
        return False, False
    if es_hash_bcrypt(hash_guardado):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hash_guardado.encode("utf-8")), False
        except ValueError:
            return False, False
    if re.fullmatch(r"[0-9a-f]{64}", hash_guardado):
        ok = hashlib.sha256(password.encode()).hexdigest() == hash_guardado
        return ok, ok
    return False, False


def validar_politica(password: str) -> list[str]:
    """Lista de incumplimientos; vacía si la contraseña es aceptable."""
    errores = []
    if len(password) < LONGITUD_MINIMA:
        errores.append(f"Debe tener al menos {LONGITUD_MINIMA} caracteres.")
    if not re.search(r"[A-Z]", password):
        errores.append("Debe incluir una letra mayúscula.")
    if not re.search(r"[a-z]", password):
        errores.append("Debe incluir una letra minúscula.")
    if not re.search(r"\d", password):
        errores.append("Debe incluir un número.")
    if not re.search(r"[^A-Za-z0-9]", password):
        errores.append("Debe incluir un carácter especial.")
    return errores
