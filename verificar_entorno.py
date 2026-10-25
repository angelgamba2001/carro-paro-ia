"""Verifica que el entorno tenga lo necesario. Uso: python verificar_entorno.py"""
import importlib
import shutil
import subprocess  # nosec B404 - se usa con lista fija, sin shell y con ruta resuelta por shutil.which
import sys

print(f"Python {sys.version.split()[0]}", "✔" if (3, 10) <= sys.version_info[:2] <= (3, 12) else
      "⚠ se recomienda 3.10–3.12 (PySpark 3.5)")
# Se importa el submódulo que el proyecto usa realmente, no solo el paquete raíz.
# `import sklearn` funciona aunque `sklearn.ensemble` esté roto: los módulos
# compilados (.pyd) solo se cargan al entrar en el submódulo, y son justo los que
# fallan cuando NumPy y scikit-learn no son de versiones compatibles entre sí.
#   (módulo a importar, paquete del que leer la versión)
COMPROBAR = [
    ("streamlit", None), ("plotly", None), ("fastapi", None), ("uvicorn", None),
    ("mysql.connector", None), ("bcrypt", None), ("jwt", None), ("pandas", None),
    ("pyarrow", None), ("numpy", None),
    ("sklearn.ensemble", "sklearn"),        # aquí están los módulos compilados
    ("pyspark", None), ("xlsxwriter", None), ("dotenv", None),
]

roto = []
for mod, paquete in COMPROBAR:
    try:
        m = importlib.import_module(mod)
        version = getattr(importlib.import_module(paquete or mod), "__version__", "")
        print(f"  ✔ {(paquete or mod)} {version}")
    except ImportError as e:
        # Distinguir «no está instalado» de «está instalado pero no carga»
        if "No module named" in str(e):
            print(f"  ✖ {(paquete or mod)} no instalado")
        else:
            print(f"  ✖ {(paquete or mod)} instalado pero NO carga: {str(e)[:90]}")
            roto.append(paquete or mod)
    except Exception as e:                    # noqa: BLE001
        print(f"  ✖ {(paquete or mod)} falla al importar: {type(e).__name__}: {str(e)[:80]}")
        roto.append(paquete or mod)

if roto:
    print("\n  ─────────────────────────────────────────────────────────────")
    print("  Hay paquetes instalados que no cargan. La causa habitual es que")
    print("  NumPy se actualizó después de instalarlos: los módulos compilados")
    print("  quedan enlazados contra la versión anterior. Se corrige con:")
    print("\n      pip install --force-reinstall --no-cache-dir numpy scipy scikit-learn")
    print("\n  El --no-cache-dir es necesario: sin él pip reinstala desde la caché")
    print("  exactamente la misma versión incompatible.")
    print("  ─────────────────────────────────────────────────────────────\n")
for opcional in ["easyocr"]:
    try:
        importlib.import_module(opcional)
        print(f"  ✔ {opcional} (opcional)")
    except ImportError:
        print(f"  – {opcional} no instalado (opcional: lectura OCR de imágenes)")

java = shutil.which("java")
if java:
    # nosec B603 - orden fija de dos elementos, sin shell; 'java' lo resuelve shutil.which
    salida = subprocess.run([java, "-version"],  # nosec B603
                            capture_output=True, text=True).stderr.splitlines()[0]
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
