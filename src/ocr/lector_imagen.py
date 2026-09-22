"""Lectura de texto en fotos de ampollas/cajas con EasyOCR (se carga solo cuando se usa)."""
from functools import lru_cache


@lru_cache(maxsize=1)
def _lector():
    import easyocr  # importación diferida: el modelo pesa varios cientos de MB
    return easyocr.Reader(["es", "en"], gpu=False)


def ocr_disponible() -> bool:
    try:
        import easyocr  # noqa: F401
        return True
    except Exception:
        return False


def leer_texto(imagen_bytes: bytes) -> tuple[str, float]:
    """Retorna (texto concatenado, confianza promedio 0-1)."""
    resultados = _lector().readtext(imagen_bytes)
    if not resultados:
        return "", 0.0
    texto = " ".join(r[1] for r in resultados)
    confianza = sum(r[2] for r in resultados) / len(resultados)
    return texto, round(float(confianza), 3)
