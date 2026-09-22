"""Verifica que el entorno tenga lo necesario. Uso: python verificar_entorno.py"""
import importlib
import shutil
import subprocess
import sys

print(f"Python {sys.version.split()[0]}", "✔" if (3, 10) <= sys.version_info[:2] <= (3, 12) else
      "⚠ se recomienda 3.10–3.12 (PySpark 3.5)")
for mod in ["streamlit", "plotly", "fastapi", "uvicorn", "mysql.connector", "bcrypt", "jwt", "pandas",
            "pyarrow", "sklearn", "pyspark", "xlsxwriter", "dotenv"]:
    try:
        m = importlib.import_module(mod)
        print(f"  ✔ {mod} {getattr(m, '__version__', '')}")
    except ImportError:
        print(f"  ✖ {mod} no instalado")
for opcional in ["easyocr"]:
    try:
        importlib.import_module(opcional)
        print(f"  ✔ {opcional} (opcional)")
    except ImportError:
        print(f"  – {opcional} no instalado (opcional: lectura OCR de imágenes)")

java = shutil.which("java")
if java:
    salida = subprocess.run([java, "-version"], capture_output=True, text=True).stderr.splitlines()[0]
    print(f"Java: {salida} ✔")
else:
    print("Java no encontrado: el pipeline usará el motor pandas (instale JDK 17 para Spark)")

sys.path.insert(0, ".")
from src.database.connection import base_disponible  # noqa: E402
print("MySQL:", "conexión OK ✔" if base_disponible() else "✖ sin conexión (revise .env)")
