"""
Registro de la aceptación de las políticas (Ley 1581 de 2012, art. 9: el responsable
debe poder demostrar que obtuvo la autorización del titular).

Se guarda quién aceptó, qué versión y cuándo. Al cambiar los documentos legales se
sube VERSION_POLITICAS y el sistema vuelve a pedir la aceptación en el siguiente ingreso.
"""
import logging

from src.database.connection import consultar, ejecutar

log = logging.getLogger(__name__)

# Súbala cuando cambie el contenido de app/legal.py
VERSION_POLITICAS = "1.0"

TEXTO_ACEPTACION = ("He leído y acepto los términos y condiciones, la política de privacidad y la "
                    "política de cookies.")


def registrar_aceptacion(usuario_id: int, origen: str = "WEB", version: str | None = None) -> bool:
    """Deja constancia de la aceptación. No interrumpe el ingreso si falla el registro."""
    version = version or VERSION_POLITICAS
    try:
        ya = consultar("SELECT id FROM consentimientos WHERE usuario_id = %s AND version = %s "
                       "AND revocado = 0", (usuario_id, version), uno=True)
        if ya:
            return False
        ejecutar("INSERT INTO consentimientos (usuario_id, version, documento, origen) "
                 "VALUES (%s, %s, 'politicas', %s)", (usuario_id, version, origen))
        from src.database.auditoria import registrar_log
        registrar_log(usuario_id, "ACEPTACION_POLITICAS", "consentimientos", None,
                      f"Versión {version}", origen)
        return True
    except Exception as e:
        log.error("No se pudo registrar la aceptación de políticas: %s", e)
        return False


def acepto_version_vigente(usuario_id: int) -> bool:
    try:
        r = consultar("SELECT id FROM consentimientos WHERE usuario_id = %s AND version = %s "
                      "AND revocado = 0", (usuario_id, VERSION_POLITICAS), uno=True)
        return bool(r)
    except Exception:
        return True       # ante un fallo técnico no se bloquea el acceso al sistema


def historial(usuario_id: int) -> list[dict]:
    return consultar("SELECT version, documento, fecha, origen, revocado FROM consentimientos "
                     "WHERE usuario_id = %s ORDER BY fecha DESC", (usuario_id,))
