"""
Genera el histórico 'legado' que se deposita en la zona RAW del data lake:
revisiones diarias del carro, consumos por código azul y bajas por vencimiento.

    python scripts/generar_historico.py --anios 5

Con 5 años: ~400 mil registros de revisión + consumos + bajas (ajustable con --anios).
El histórico termina donde empiezan los movimientos de la base operativa MySQL.
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.bigdata.simulador import (filas_bajas_historicas, filas_consumo_historico,  # noqa: E402
                                   filas_revision_diaria)

DIAS_OPERACION = 60


def _escribir_por_anio(nombre: str, filas, clave_fecha: str):
    base = config.RAW_DIR / nombre
    archivos, escritores, total = {}, {}, 0
    conteo = defaultdict(int)
    try:
        for f in filas:
            valor = f[clave_fecha]
            anio = valor[:4] if valor[4] == "-" else valor[6:10]
            if anio not in escritores:
                carpeta = base / f"anio={anio}"
                carpeta.mkdir(parents=True, exist_ok=True)
                archivos[anio] = open(carpeta / f"{nombre}.csv", "w", newline="", encoding="utf-8")
                escritores[anio] = csv.DictWriter(archivos[anio], fieldnames=list(f.keys()))
                escritores[anio].writeheader()
            escritores[anio].writerow(f)
            conteo[anio] += 1
            total += 1
    finally:
        for a in archivos.values():
            a.close()
    print(f"  {nombre:<20} {total:>9,} filas  ({', '.join(f'{k}:{v:,}' for k, v in sorted(conteo.items()))})")
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--anios", type=int, default=5)
    a = ap.parse_args()
    hasta = date.today() - timedelta(days=DIAS_OPERACION + 1)
    desde = hasta - timedelta(days=365 * a.anios)
    print(f"Generando histórico {desde} -> {hasta} en {config.RAW_DIR}")
    total = 0
    total += _escribir_por_anio("revisiones", filas_revision_diaria(desde, hasta), "fecha")
    total += _escribir_por_anio("consumos", filas_consumo_historico(desde, hasta), "fecha_hora")
    total += _escribir_por_anio("bajas", filas_bajas_historicas(desde, hasta), "fecha")
    print(f"Total: {total:,} registros")


if __name__ == "__main__":
    main()
