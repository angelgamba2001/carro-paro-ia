"""
Orquesta la analítica sobre GOLD y la devuelve a la operación:
predicción -> riesgo de desabastecimiento -> anomalías -> matriz de riesgo -> alertas en MySQL.
"""
import pandas as pd

from src import config
from src.analitica.anomalias import detectar_anomalias
from src.analitica.prediccion import cruzar_con_stock, entrenar_y_predecir, guardar_metricas
from src.analitica.riesgo import evaluar
from src.database.connection import conexion, consultar_df
from src.servicios.alertas import crear_alerta
from src.servicios.inventario import recalcular_estados, stock_por_carro

_SISTEMA = {"id": 0, "rol": "ADMIN", "activo": 1, "correo": "sistema"}  # proceso interno


def ejecutar_analitica() -> dict:
    recalcular_estados()
    pred, metricas = entrenar_y_predecir()
    guardar_metricas(metricas)
    cruce = cruzar_con_stock(pred, stock_por_carro(_SISTEMA))
    cruce.to_parquet(config.GOLD_DIR / "predicciones.parquet", index=False)

    anom = detectar_anomalias()
    anom.to_parquet(config.GOLD_DIR / "anomalias.parquet", index=False)

    proximos = consultar_df("""SELECT carro_id, medicamento_id, SUM(cantidad) AS unidades_proximas
                               FROM inventario_carro WHERE estado='proximo_a_vencer' GROUP BY carro_id, medicamento_id""")
    if proximos.empty:
        proximos = pd.DataFrame(columns=["carro_id", "medicamento_id", "unidades_proximas"])
    riesgo = evaluar(cruce, proximos)
    riesgo.to_parquet(config.GOLD_DIR / "riesgo.parquet", index=False)

    with conexion() as conn:
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO predicciones_demanda (carro_id, medicamento_id, horizonte_dias, demanda_estimada, "
            "stock_actual, dias_cobertura, riesgo_desabastecimiento) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            [(int(r.carro_id), int(r.medicamento_id), metricas["horizonte_dias"], float(r.demanda_estimada),
              int(r.stock), float(min(r.dias_cobertura, 999)), int(r.riesgo_desabastecimiento))
             for r in cruce.itertuples()])
        cur.executemany(
            "INSERT INTO historial_riesgo (carro_id, medicamento_id, probabilidad, impacto, puntaje_riesgo, "
            "nivel_riesgo, justificacion) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            [(int(r.carro_id), int(r.medicamento_id), int(r.probabilidad), int(r.impacto), int(r.puntaje_riesgo),
              r.nivel_riesgo, r.justificacion[:255]) for r in riesgo.itertuples()])
        cur.close()

    nuevas = 0
    for r in cruce[cruce["riesgo_desabastecimiento"] == 1].itertuples():
        if crear_alerta("RIESGO_DESABASTECIMIENTO",
                        f"{r.medicamento} en {r.carro}: stock {r.stock}, demanda {r.demanda_estimada:.1f} "
                        f"en {metricas['horizonte_dias']} días. Reponer {r.unidades_a_reponer} ud.",
                        "ALTA" if r.criticidad == "ALTA" else "MEDIA", "ANALITICA",
                        carro_id=int(r.carro_id), medicamento_id=int(r.medicamento_id)):
            nuevas += 1
    carros = consultar_df("SELECT id, codigo FROM carros").set_index("codigo")["id"].to_dict()
    meds = consultar_df("SELECT id, nombre FROM cat_medicamentos").set_index("nombre")["id"].to_dict()
    for r in anom.head(20).itertuples():
        if crear_alerta("CONSUMO_ANOMALO", f"{r.medicamento} en {r.carro}: {r.motivo}", "MEDIA", "ANALITICA",
                        carro_id=carros.get(r.carro), medicamento_id=meds.get(r.medicamento)):
            nuevas += 1

    return {"metricas_modelo": metricas,
            "series_con_riesgo": int(cruce["riesgo_desabastecimiento"].sum()),
            "anomalias_recientes": int(len(anom)),
            "riesgo_alto": int((riesgo["nivel_riesgo"] == "ALTO").sum()),
            "alertas_nuevas": nuevas}
