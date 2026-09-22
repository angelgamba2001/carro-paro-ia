"""
Detección de consumos anómalos (Isolation Forest).

Un consumo semanal es sospechoso si se aleja mucho del comportamiento histórico del
mismo carro-medicamento (z-score), o si las unidades por evento de código azul son
inusuales. Útil para detectar errores de registro, pérdidas o uso no documentado.
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.bigdata.procesamiento import leer_gold

SEMANAS_REVISION = 8


def detectar_anomalias(contaminacion: float = 0.01) -> pd.DataFrame:
    s = leer_gold("consumo_semanal")
    if s.empty:
        return pd.DataFrame()
    s["semana"] = pd.to_datetime(s["semana"])
    s = s.sort_values(["carro", "medicamento", "semana"])
    g = s.groupby(["carro", "medicamento"])["unidades"]
    media = g.transform(lambda x: x.shift(1).rolling(26, min_periods=4).mean())
    desv = g.transform(lambda x: x.shift(1).rolling(26, min_periods=4).std())
    s["zscore"] = ((s["unidades"] - media) / (desv.fillna(0) + 1)).fillna(0)
    s["unidades_por_evento"] = s["unidades"] / s["eventos"].replace(0, np.nan)
    s["unidades_por_evento"] = s["unidades_por_evento"].fillna(s["unidades"])
    X = s[["unidades", "zscore", "unidades_por_evento", "eventos"]]
    modelo = IsolationForest(n_estimators=200, contamination=contaminacion, random_state=42)
    s["anomalia"] = modelo.fit_predict(X) == -1
    s["puntaje"] = -modelo.score_samples(X)
    recientes = s["semana"] >= s["semana"].max() - pd.Timedelta(weeks=SEMANAS_REVISION)
    res = s[recientes & s["anomalia"] & (s["zscore"] > 2)].copy()
    res["motivo"] = [f"{int(u)} ud en la semana; {z:.1f} desviaciones sobre su promedio"
                     for u, z in zip(res["unidades"], res["zscore"])]
    return res.sort_values("puntaje", ascending=False)[
        ["semana", "carro", "servicio", "medicamento", "unidades", "eventos", "zscore", "puntaje", "motivo"]]
