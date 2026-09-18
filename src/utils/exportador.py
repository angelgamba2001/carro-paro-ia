import pandas as pd
import io

def generar_csv(df: pd.DataFrame) -> bytes:
    """Convierte un DataFrame de pandas a formato CSV codificado en UTF-8."""
    return df.to_csv(index=False).encode('utf-8-sig')

def generar_excel(df: pd.DataFrame) -> bytes:
    """Convierte un DataFrame de pandas a un archivo ejecutable en memoria de Excel (.xlsx)."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Reporte')
    return output.getvalue()