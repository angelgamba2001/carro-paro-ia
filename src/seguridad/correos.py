"""
Qué direcciones de correo admite el sistema.

Hasta ahora bastaba con que el texto tuviera una arroba, lo que servía para los
usuarios de demostración pero no para una institución real. Aquí se valida el
formato y, si la institución lo exige, que el dominio esté en la lista permitida.

La lista vive en el .env (DOMINIOS_CORREO). Vacía significa "cualquier dominio
válido", que es lo razonable para un despliegue de prueba; en producción se
restringe al dominio corporativo para que nadie cree cuentas con un correo suyo.
"""
import re

from src import config

# No se valida con la gramática completa del RFC 5322: es enorme y acepta cosas
# que ningún proveedor real entrega. Esta expresión cubre lo que Microsoft 365 y
# Google aceptan, que es el criterio útil.
PATRON = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Dominios de correo personal: se permiten o no según la configuración, pero se
# reconocen aparte para poder advertir al administrador que está creando una
# cuenta institucional con una dirección personal.
PERSONALES = {"gmail.com", "hotmail.com", "outlook.com", "outlook.es", "live.com",
              "yahoo.com", "yahoo.es", "icloud.com", "protonmail.com", "proton.me"}


def normalizar(correo: str) -> str:
    """Minúsculas y sin espacios. Es la forma en que se guarda y se compara."""
    return (correo or "").strip().lower()


def dominio(correo: str) -> str:
    return normalizar(correo).rpartition("@")[2]


def dominios_permitidos() -> list[str]:
    """Lista configurada, ya normalizada. Vacía = se acepta cualquier dominio."""
    crudo = config.DOMINIOS_CORREO or ""
    return [d.strip().lower().lstrip("@") for d in crudo.split(",") if d.strip()]


def es_personal(correo: str) -> bool:
    return dominio(correo) in PERSONALES


def validar(correo: str) -> str:
    """Devuelve el correo normalizado o levanta ValueError con el motivo.

    Se usa al crear y al editar usuarios. NO se usa al iniciar sesión: una cuenta
    ya creada debe poder entrar aunque después se restrinja la lista de dominios,
    porque si no, un cambio de configuración deja gente fuera sin avisar.
    """
    correo = normalizar(correo)
    if not correo:
        raise ValueError("El correo es obligatorio.")
    if len(correo) > 255:
        raise ValueError("El correo es demasiado largo.")
    if not PATRON.match(correo):
        raise ValueError("El correo no tiene un formato válido. Ejemplo: nombre.apellido@dominio.com")

    permitidos = dominios_permitidos()
    if permitidos and dominio(correo) not in permitidos:
        cuales = ", ".join("@" + d for d in permitidos)
        raise ValueError(f"Solo se admiten correos de: {cuales}")
    return correo
