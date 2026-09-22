"""Matriz de riesgo probabilidad x impacto (1-5) por carro y medicamento -> historial_riesgo."""
import pandas as pd

IMPACTO = {"ALTA": 5, "MEDIA": 3, "BAJA": 2}


def evaluar(cruce: pd.DataFrame, proximos: pd.DataFrame) -> pd.DataFrame:
    """cruce: salida de prediccion.cruzar_con_stock; proximos: unidades próximas a vencer por carro-med."""
    df = cruce.merge(proximos, on=["carro_id", "medicamento_id"], how="left").fillna({"unidades_proximas": 0})
    filas = []
    for _, r in df.iterrows():
        prob, motivos = 1, []
        if r["stock"] < r["stock_minimo"]:
            prob = 5; motivos.append("stock bajo el mínimo")
        elif r["riesgo_desabastecimiento"]:
            prob = 4; motivos.append("demanda prevista supera el stock disponible")
        elif r["dias_cobertura"] < 30:
            prob = 3; motivos.append(f"cobertura de {r['dias_cobertura']:.0f} días")
        if r["stock"] and r["unidades_proximas"] / max(r["stock"], 1) >= 0.5:
            prob = max(prob, 3); motivos.append("más de la mitad del stock vence pronto")
        imp = IMPACTO.get(r["criticidad"], 3)
        puntaje = prob * imp
        nivel = "ALTO" if puntaje >= 15 else ("MEDIO" if puntaje >= 8 else "BAJO")
        filas.append({"carro_id": r["carro_id"], "carro": r["carro"], "medicamento_id": r["medicamento_id"],
                      "medicamento": r["medicamento"], "probabilidad": prob, "impacto": imp,
                      "puntaje_riesgo": puntaje, "nivel_riesgo": nivel,
                      "justificacion": "; ".join(motivos) or "sin factores de riesgo"})
    return pd.DataFrame(filas)
