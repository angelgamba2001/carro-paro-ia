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
import mysql.connector  # noqa: E402

from src import config  # noqa: E402

# Se conecta SIN indicar la base, para poder distinguir "MySQL no responde" de
# "MySQL responde pero la base todavía no existe". Decir solo "sin conexión" en
# el segundo caso manda a revisar el .env cuando lo que falta es inicializar_bd.
try:
    cnx = mysql.connector.connect(host=config.DB_HOST, port=config.DB_PORT,
                                  user=config.DB_USER, password=config.DB_PASSWORD,
                                  connection_timeout=6)
    cur = cnx.cursor()
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                (config.DB_NAME,))
    tablas = cur.fetchone()[0]
    cur.close()
    cnx.close()
    if tablas == 0:
        print(f"MySQL: responde ✔ pero la base {config.DB_NAME} aún no existe")
        print("       Ejecute:  python scripts/inicializar_bd.py")
    else:
        print(f"MySQL: conexión OK ✔ ({config.DB_NAME}, {tablas} tablas)")
except mysql.connector.Error as e:
    print(f"MySQL: ✖ sin conexión — error {e.errno}: {e.msg}")
    print("       Detalle y remedio:  python diagnostico_mysql.py")
