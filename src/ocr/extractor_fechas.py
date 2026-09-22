"""
Extracción de fecha de vencimiento y lote desde el texto leído por OCR.

Corrige un defecto de la v1: el patrón MM/AAAA se evaluaba antes que la fecha completa,
por lo que '12/05/2027' se interpretaba como diciembre de 2005.
"""
import re
from datetime import date

MESES = {"ENE": 1, "JAN": 1, "FEB": 2, "MAR": 3, "ABR": 4, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7,
         "AGO": 8, "AUG": 8, "SEP": 9, "SET": 9, "OCT": 10, "NOV": 11, "DIC": 12, "DEC": 12}

_CLAVE_VENC = r"(?:EXP|VENC|VTO|VEN|CAD|FV|F\.?\s?V\.?)"


def _valida(anio: int, mes: int, dia: int = 1) -> str | None:
    if anio < 100:
        anio += 2000
    try:
        return date(anio, mes, dia).isoformat()
    except ValueError:
        return None


def extraer_fecha_texto(texto: str) -> str | None:
    """Devuelve la fecha en formato YYYY-MM-DD (MySQL) o None. Si solo hay mes/año, usa el día 1."""
    if not texto:
        return None
    t = texto.upper().replace("\n", " ")
    # Prioriza lo que sigue a una palabra clave de vencimiento (evita tomar la fecha de fabricación)
    m = re.search(_CLAVE_VENC + r"[\s.:]*([0-9A-Z/.\- ]{4,14})", t)
    candidatos = [m.group(1)] if m else []
    candidatos.append(t)
    for c in candidatos:
        # 1) fecha completa AAAA-MM-DD o DD/MM/AAAA
        f = re.search(r"\b(20\d{2})[/\-.](0?[1-9]|1[0-2])[/\-.](0?[1-9]|[12]\d|3[01])\b", c)
        if f and (r := _valida(int(f[1]), int(f[2]), int(f[3]))):
            return r
        f = re.search(r"\b(0?[1-9]|[12]\d|3[01])[/\-.](0?[1-9]|1[0-2])[/\-.](20\d{2}|\d{2})\b", c)
        if f and (r := _valida(int(f[3]), int(f[2]), int(f[1]))):
            return r
        # 2) mes/año numérico MM/AAAA o MM/AA
        f = re.search(r"\b(0?[1-9]|1[0-2])[/\-.](20\d{2}|\d{2})\b", c)
        if f and (r := _valida(int(f[2]), int(f[1]))):
            return r
        # 3) mes en texto: NOV 2027, NOV-27
        f = re.search(r"\b(" + "|".join(MESES) + r")[\s/\-.]*(20\d{2}|\d{2})\b", c)
        if f and (r := _valida(int(f[2]), MESES[f[1]])):
            return r
    return None


def extraer_lote(texto: str) -> str | None:
    if not texto:
        return None
    m = re.search(r"\b(?:LOTE|LOT|LT|L)[\s.:#]*([A-Z0-9\-]{3,20})", texto.upper())
    return m.group(1) if m else None
