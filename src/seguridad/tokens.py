"""JWT para la API (HU14). Firma HS256, expiración corta y jti único."""
import uuid
from datetime import datetime, timedelta, timezone

import jwt

from src import config

ALGORITMO = "HS256"


def _secreto() -> str:
    if config.JWT_SECRETO:
        return config.JWT_SECRETO
    if config.ENTORNO == "produccion":
        raise RuntimeError("JWT_SECRETO no está configurado.")
    return "solo-desarrollo-cambiar-en-.env"


def emitir_token(usuario: dict, mfa_pendiente: bool = False) -> str:
    """mfa_pendiente=True emite un token temporal (5 min) que SOLO sirve para enviar
    el código del segundo factor; no da acceso a ningún recurso."""
    ahora = datetime.now(timezone.utc)
    minutos = 5 if mfa_pendiente else config.JWT_MINUTOS_EXPIRACION
    payload = {
        "sub": str(usuario["id"]),
        "rol": usuario["rol"],       # sin datos personales en el token
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos),
        "jti": uuid.uuid4().hex,
    }
    if mfa_pendiente:
        payload["mfa"] = "pendiente"
    return jwt.encode(payload, _secreto(), algorithm=ALGORITMO)


def decodificar_token(token: str) -> dict:
    """Lanza jwt.InvalidTokenError si el token es inválido, manipulado o expiró."""
    return jwt.decode(token, _secreto(), algorithms=[ALGORITMO])
