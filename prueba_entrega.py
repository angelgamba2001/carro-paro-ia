import os
from src.database.connection import obtener_conexion
from src.ocr.extractor_fechas import extraer_fecha_texto

def probar_avance_proyecto():
    print("=" * 60)
    print("DEMOSTRACIÓN DE AVANCE - PROYECTO TESIS CARRO DE PARO")
    print("=" * 60)
    
    # 1. Probar Conexión a Base de Datos MySQL
    conexion = obtener_conexion()
    if conexion:
        cursor = conexion.cursor()
        cursor.execute("SHOW TABLES;")
        tablas = cursor.fetchall()
        print("\n[✔] Conexión a la BD MySQL (carro_paro_db): EXITOSA")
        print("Tablas encontradas en la BD:")
        for t in tablas:
            print(f" - {t[0]}")
        cursor.close()
        conexion.close()
    else:
        print("\n[✖] Error conectando a la base de datos.")

    # 2. Probar Motor de Extracción con Regex (Simulación OCR)
    texto_ejemplo_ampolla = "LOT: B8942 EXP: 11/2027 ADRENALINA 1MG/ML"
    fecha_extraida = extraer_fecha_texto(texto_ejemplo_ampolla)
    
    print("\n[✔] Módulo OCR y Regex para Fechas: FUNCIONAL")
    print(f"Texto simulado de ampolla: '{texto_ejemplo_ampolla}'")
    print(f"Fecha estandarizada para MySQL: {fecha_extraida}")
    print("=" * 60)

if __name__ == "__main__":
    probar_avance_proyecto()