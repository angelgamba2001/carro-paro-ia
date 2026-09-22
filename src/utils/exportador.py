import io

import pandas as pd


def generar_csv(df: pd.DataFrame) -> bytes:
    """CSV UTF-8 con BOM (abre bien en Excel con tildes)."""
    return df.to_csv(index=False).encode("utf-8-sig")


def generar_excel(df: pd.DataFrame) -> bytes:
    salida = io.BytesIO()
    with pd.ExcelWriter(salida, engine="xlsxwriter") as w:
        df.to_excel(w, index=False, sheet_name="Reporte")
    return salida.getvalue()
