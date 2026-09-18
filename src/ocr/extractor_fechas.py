import re

def extraer_fecha_texto(texto: str):
    """
    Busca patrones de fechas en un texto detectado y las convierte
    al formato estándar de MySQL (YYYY-MM-DD).
    """
    patron_mes_anio = r'\b(0[1-9]|1[0-2])[/-](20\d{2}|\d{2})\b'
    patron_completo = r'\b(\d{2,4})[/-](\d{2})[/-](\d{2,4})\b'

    match_mes_anio = re.search(patron_mes_anio, texto)
    if match_mes_anio:
        mes, anio = match_mes_anio.groups()
        if len(anio) == 2:
            anio = f"20{anio}"
        return f"{anio}-{mes}-01"

    match_completo = re.search(patron_completo, texto)
    if match_completo:
        p1, p2, p3 = match_completo.groups()
        if len(p1) == 4:
            return f"{p1}-{p2}-{p3}"
        elif len(p3) == 4:
            return f"{p3}-{p2}-{p1}"

    