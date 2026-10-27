"""
Cifrado en reposo de secretos que no pueden guardarse con hash (porque hay que
volver a leerlos): hoy, el secreto del segundo factor TOTP.

Usa Fernet (AES-128-CBC + HMAC-SHA256). Los valores cifrados llevan el prefijo
"enc:" para distinguirlos de los antiguos, guardados en claro: se siguen leyendo
y se cifran la próxima vez que se escriban (o al ejecutar scripts/migrar_seguridad.py).

La clave sale de CLAVE_CIFRADO; si falta, se deriva de JWT_SECRETO. En producción
debe existir una de las dos: sin clave no se guarda ningún secreto en claro.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from src import config

PREFIJO = "enc:"


def _clave() -> bytes:
    if config.CLAVE_CIFRADO:
        return config.CLAVE_CIFRADO.encode()
    base = config.JWT_SECRETO
    if not base:
        if config.ENTORNO == "produccion":
            raise RuntimeError("Falta CLAVE_CIFRADO (o JWT_SECRETO) para cifrar los secretos.")
        base = "solo-desarrollo-cambiar-en-.env"
    return base64.urlsafe_b64encode(hashlib.sha256(("cifrado:" + base).encode()).digest())


def esta_cifrado(valor: str | None) -> bool:
    return bool(valor) and valor.startswith(PREFIJO)


def cifrar(texto: str | None) -> str | None:
    if not texto:
        return texto
    if esta_cifrado(texto):
        return texto
    return PREFIJO + Fernet(_clave()).encrypt(texto.encode()).decode()


def descifrar(valor: str | None) -> str | None:
    """Devuelve el texto en claro. Un valor sin prefijo es un secreto antiguo y se devuelve igual."""
    if not valor or not esta_cifrado(valor):
        return valor
    try:
        return Fernet(_clave()).decrypt(valor[len(PREFIJO):].encode()).decode()
    except InvalidToken as e:
        raise ValueError("No se pudo descifrar el secreto: la clave de cifrado cambió.") from e
