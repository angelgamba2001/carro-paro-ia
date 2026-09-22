"""
Predicción de demanda y riesgo de desabastecimiento por carro y medicamento.

Modelo: HistGradientBoostingRegressor global (un solo modelo para todas las series
carro-medicamento) sobre consumo SEMANAL de la zona GOLD. Variables: rezagos,
medias móviles, estacionalidad (semana del año) y códigos de carro/medicamento/servicio.
Objetivo: unidades consumidas en las próximas 2 semanas (horizonte de reposición).

Se evalúa contra una línea base ingenua (media de las últimas 4 semanas) en las
últimas 26 semanas, que no se usan para entrenar. Si el modelo no supera la línea
base, se reporta honestamente en las métricas.
"""
import json
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

from src import config
from src.bigdata.procesamiento import leer_gold

SEMANAS_PRUEBA = 26
HORIZONTE_SEMANAS = 2


def _panel_semanal() -> pd.DataFrame:
    s = leer_gold("consumo_semanal")
    if s.empty:
        raise RuntimeError("No hay datos GOLD. Ejecute el pipeline Big Data primero.")
    s["semana"] = pd.to_datetime(s["semana"])
    ultima_completa = (pd.Timestamp.today().normalize() - pd.Timedelta(days=7)).to_period("W-SUN").start_time
    semanas = pd.date_range(s["semana"].min(), ultima_completa, freq="W-MON")
    pares = s[["carro", "servicio", "medicamento"]].drop_duplicates()
    idx = pares.merge(pd.DataFrame({"semana": semanas}), how="cross")
    p = idx.merge(s[["semana", "carro", "medicamento", "unidades", "eventos"]],
                  on=["semana", "carro", "medicamento"], how="left").fillna({"unidades": 0, "eventos": 0})
    return p.sort_values(["carro", "medicamento", "semana"]).reset_index(drop=True)


def _variables(p: pd.DataFrame) -> pd.DataFrame:
    g = p.groupby(["carro", "medicamento"])["unidades"]
    for k in range(4):
        p[f"lag{k}"] = g.shift(k)
    p["media4"] = g.transform(lambda x: x.rolling(4, min_periods=1).mean())
    p["media12"] = g.transform(lambda x: x.rolling(12, min_periods=1).mean())
    p["media52"] = g.transform(lambda x: x.rolling(52, min_periods=4).mean())
    semana_anio = p["semana"].dt.isocalendar().week.astype(int)
    p["sen"] = np.sin(2 * np.pi * semana_anio / 52)
    p["cos"] = np.cos(2 * np.pi * semana_anio / 52)
    for c in ("carro", "medicamento", "servicio"):
        p[f"{c}_cod"] = p[c].astype("category").cat.codes
    p["objetivo"] = sum(g.shift(-h) for h in range(1, HORIZONTE_SEMANAS + 1))
    return p


COLUMNAS = ["lag0", "lag1", "lag2", "lag3", "media4", "media12", "media52", "sen", "cos",
            "carro_cod", "medicamento_cod", "servicio_cod"]


def entrenar_y_predecir() -> tuple[pd.DataFrame, dict]:
    p = _variables(_panel_semanal())
    datos = p.dropna(subset=["objetivo", "lag3", "media52"])
    corte = datos["semana"].max() - pd.Timedelta(weeks=SEMANAS_PRUEBA)
    entreno, prueba = datos[datos["semana"] <= corte], datos[datos["semana"] > corte]

    modelo = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_depth=6,
                                           categorical_features=[9, 10, 11], random_state=42)
    modelo.fit(entreno[COLUMNAS], entreno["objetivo"])
    pred_prueba = np.clip(modelo.predict(prueba[COLUMNAS]), 0, None)
    base = prueba["media4"] * HORIZONTE_SEMANAS
    metricas = {
        "fecha": datetime.now().isoformat(timespec="seconds"),
        "modelo": "HistGradientBoostingRegressor (global)",
        "horizonte_dias": HORIZONTE_SEMANAS * 7,
        "filas_entrenamiento": int(len(entreno)),
        "filas_prueba": int(len(prueba)),
        "mae_modelo": round(float(mean_absolute_error(prueba["objetivo"], pred_prueba)), 3),
        "mae_linea_base": round(float(mean_absolute_error(prueba["objetivo"], base)), 3),
    }
    metricas["mejora_vs_base_pct"] = round(100 * (1 - metricas["mae_modelo"] / metricas["mae_linea_base"]), 1) \
        if metricas["mae_linea_base"] else None

    # Re-entrenar con todo lo disponible y predecir desde la última semana
    modelo.fit(datos[COLUMNAS], datos["objetivo"])
    ultima = p[p["semana"] == p["semana"].max()].copy()
    ultima["demanda_estimada"] = np.clip(modelo.predict(ultima[COLUMNAS]), 0, None).round(2)
    pred = ultima[["carro", "servicio", "medicamento", "demanda_estimada"]].reset_index(drop=True)
    return pred, metricas


def cruzar_con_stock(pred: pd.DataFrame, stock: pd.DataFrame) -> pd.DataFrame:
    """stock: salida de servicios.inventario.stock_por_carro()."""
    df = stock.merge(pred, on=["carro", "medicamento"], how="left", suffixes=("", "_pred"))
    df["demanda_estimada"] = df["demanda_estimada"].fillna(0.0)
    diaria = df["demanda_estimada"] / (HORIZONTE_SEMANAS * 7)
    df["dias_cobertura"] = np.where(diaria > 0, (df["stock"] / diaria).round(1), 999.0)
    df["stock_proyectado"] = (df["stock"] - df["demanda_estimada"]).round(1)
    df["riesgo_desabastecimiento"] = (df["stock_proyectado"] < df["stock_minimo"]).astype(int)
    df["unidades_a_reponer"] = np.maximum(0, np.ceil(df["stock_maximo"] - df["stock_proyectado"])).astype(int)
    df.loc[df["riesgo_desabastecimiento"] == 0, "unidades_a_reponer"] = 0
    return df


def guardar_metricas(metricas: dict):
    (config.GOLD_DIR / "metricas_modelo.json").write_text(json.dumps(metricas, indent=2, ensure_ascii=False),
                                                          encoding="utf-8")


def leer_metricas() -> dict | None:
    ruta = config.GOLD_DIR / "metricas_modelo.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else None
