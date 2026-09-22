"""
Ejecuta el flujo Big Data completo desde consola (útil para programarlo con cron / Programador de tareas).

    python scripts/ejecutar_pipeline.py                 # motor según .env (spark por defecto)
    python scripts/ejecutar_pipeline.py --motor pandas
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.bigdata.orquestador import ejecutar_flujo_completo  # noqa: E402
from src.database.connection import consultar  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--motor", choices=["spark", "pandas"], default=None)
    a = ap.parse_args()
    # El proceso programado corre con la identidad de un usuario con permiso bigdata.ejecutar
    usuario = consultar("SELECT id, nombre, correo, rol, activo FROM usuarios "
                        "WHERE rol IN ('ANALISTA_DATOS','ADMIN','TI') AND activo = 1 ORDER BY rol LIMIT 1", uno=True)
    if not usuario:
        sys.exit("No hay un usuario activo con permiso para ejecutar el pipeline.")
    r = ejecutar_flujo_completo(usuario, a.motor, origen="PROGRAMADO")
    print(json.dumps({"procesamiento": r["procesamiento"], "analitica": r["analitica"]},
                     indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
