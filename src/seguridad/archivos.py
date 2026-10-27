"""
Validación de archivos subidos.

La extensión y el tipo MIME los controla quien sube el archivo, así que no prueban nada:
un ejecutable renombrado a .png conserva su contenido. Aquí se mira el contenido:

  1. tamaño máximo;
  2. firma real del archivo (PNG o JPEG), no la extensión;
  3. la extensión declarada debe corresponder a esa firma;
  4. se abre con Pillow y se verifica que sea una imagen íntegra, con dimensiones razonables
     (frena también las «bombas de descompresión»).

Si algo falla se rechaza con un mensaje claro y queda un evento ARCHIVO_RECHAZADO,
sin guardar el contenido del archivo.
"""
import io
import re

from src.database.auditoria import registrar_evento_seguridad

MAX_BYTES = 10 * 1024 * 1024
MAX_LADO = 12000          # píxeles por lado

FIRMAS = {
    "png": (b"\x89PNG\r\n\x1a\n",),
    "jpeg": (b"\xff\xd8\xff",),
}
EXTENSIONES = {"png": {"png"}, "jpeg": {"jpg", "jpeg"}}
# Cabeceras de programas: se nombran aparte para dar un mensaje útil
EJECUTABLES = {b"MZ": "ejecutable de Windows", b"\x7fELF": "ejecutable de Linux",
               b"#!": "script", b"PK\x03\x04": "archivo comprimido", b"%PDF": "documento PDF"}


class ArchivoInvalido(ValueError):
    """El archivo no es una imagen válida; el mensaje es apto para mostrar a la persona."""


def _nombre_seguro(nombre: str) -> str:
    return re.sub(r"[^A-Za-z0-9._\- ]", "_", nombre or "")[:80]


def _rechazar(motivo: str, nombre: str, usuario: dict | None, mensaje: str):
    registrar_evento_seguridad("ARCHIVO_RECHAZADO", (usuario or {}).get("correo"), (usuario or {}).get("id"),
                               f"{motivo}; archivo: {_nombre_seguro(nombre)}")
    raise ArchivoInvalido(mensaje)


def validar_imagen(datos: bytes, nombre: str = "", usuario: dict | None = None) -> str:
    """Devuelve 'png' o 'jpeg' si el contenido es una imagen válida; si no, levanta ArchivoInvalido."""
    if not datos:
        _rechazar("vacío", nombre, usuario, "El archivo está vacío.")
    if len(datos) > MAX_BYTES:
        _rechazar("demasiado grande", nombre, usuario, "El archivo supera los 10 MB permitidos.")

    formato = next((f for f, firmas in FIRMAS.items() if any(datos.startswith(x) for x in firmas)), None)
    if not formato:
        for cabecera, que in EJECUTABLES.items():
            if datos.startswith(cabecera):
                _rechazar(f"contenido: {que}", nombre, usuario,
                          f"El archivo no es una imagen: su contenido es un {que} con extensión cambiada.")
        _rechazar("firma desconocida", nombre, usuario, "El archivo no es una imagen PNG o JPG válida.")

    extension = (nombre.rsplit(".", 1)[-1].lower() if "." in (nombre or "") else "")
    if extension not in EXTENSIONES[formato]:
        _rechazar("extensión no coincide", nombre, usuario,
                  f"La extensión del archivo no corresponde a su contenido (es {formato.upper()}).")

    try:
        from PIL import Image
        with Image.open(io.BytesIO(datos)) as img:
            ancho, alto = img.size
            img.verify()
    except Exception:                                                  # noqa: BLE001
        _rechazar("imagen corrupta", nombre, usuario, "La imagen está dañada o no se puede leer.")
    if ancho > MAX_LADO or alto > MAX_LADO or ancho < 1 or alto < 1:
        _rechazar("dimensiones", nombre, usuario, "La imagen tiene dimensiones fuera de lo permitido.")
    return formato
