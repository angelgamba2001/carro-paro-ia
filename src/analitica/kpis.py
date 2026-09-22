"""Indicadores del tablero. Operativos desde MySQL (tiempo real) y analíticos desde GOLD."""
from datetime import date

import pandas as pd

from src.bigdata.procesamiento import leer_gold
from src.database.connection import consultar


def kpis_operativos() -> dict:
    inv = consultar("""
        SELECT COALESCE(SUM(cantidad),0) AS unidades,
               COALESCE(SUM(CASE WHEN estado='vigente' THEN cantidad END),0) AS vigentes,
               COALESCE(SUM(CASE WHEN estado='proximo_a_vencer' THEN cantidad END),0) AS proximas,
               COALESCE(SUM(CASE WHEN estado='vencido' THEN cantidad END),0) AS vencidas,
               COALESCE(SUM(CASE WHEN i.estado IN ('proximo_a_vencer','vencido') THEN i.cantidad*m.costo_unitario END),0)
                   AS valor_en_riesgo
        FROM inventario_carro i JOIN cat_medicamentos m ON m.id = i.medicamento_id
        WHERE i.estado NOT IN ('agotado','dado_de_baja')""", uno=True)
    carros = consultar("""
        SELECT x.carro_id, MIN(x.stock >= x.stock_minimo) AS completo FROM (
            SELECT c.id AS carro_id, m.stock_minimo,
                   COALESCE(SUM(CASE WHEN i.estado IN ('vigente','proximo_a_vencer') THEN i.cantidad END),0) AS stock
            FROM carros c CROSS JOIN cat_medicamentos m
            LEFT JOIN inventario_carro i ON i.carro_id=c.id AND i.medicamento_id=m.id
            WHERE c.activo=1 AND m.activo=1 AND m.criticidad='ALTA'
            GROUP BY c.id, m.id, m.stock_minimo) x GROUP BY x.carro_id""")
    alertas = consultar("""SELECT COUNT(*) AS pendientes, COALESCE(SUM(severidad='ALTA'),0) AS altas,
                                  AVG(CASE WHEN atendida=1 THEN TIMESTAMPDIFF(HOUR, fecha_generada, fecha_atencion) END)
                                      AS horas_atencion
                           FROM alertas WHERE atendida = 0 OR fecha_atencion >= DATE_SUB(NOW(), INTERVAL 30 DAY)""",
                        uno=True)
    pend = consultar("SELECT COUNT(*) AS n, COALESCE(SUM(severidad='ALTA'),0) AS altas FROM alertas WHERE atendida=0",
                     uno=True)
    consumo = consultar("""
        SELECT COALESCE(SUM(CASE WHEN fecha >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN cantidad END),0) AS ult30,
               COALESCE(SUM(CASE WHEN fecha <  DATE_SUB(NOW(), INTERVAL 30 DAY)
                                  AND fecha >= DATE_SUB(NOW(), INTERVAL 60 DAY) THEN cantidad END),0) AS prev30,
               COUNT(DISTINCT CASE WHEN fecha >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN motivo END) AS eventos30
        FROM movimientos WHERE tipo='CONSUMO'""", uno=True)
    total_carros = len(carros) or 1
    completos = sum(int(c["completo"]) for c in carros)
    ult, prev = float(consumo["ult30"]), float(consumo["prev30"])
    return {
        "unidades": int(inv["unidades"]),
        "unidades_vigentes": int(inv["vigentes"]),
        "unidades_proximas": int(inv["proximas"]),
        "unidades_vencidas": int(inv["vencidas"]),
        "valor_en_riesgo": float(inv["valor_en_riesgo"]),
        "carros_completos": completos,
        "total_carros": len(carros),
        "disponibilidad_pct": round(100 * completos / total_carros, 1),
        "alertas_pendientes": int(pend["n"]),
        "alertas_altas": int(pend["altas"]),
        "horas_promedio_atencion": round(float(alertas["horas_atencion"]), 1) if alertas["horas_atencion"] else None,
        "consumo_30d": int(ult),
        "variacion_consumo_pct": round(100 * (ult - prev) / prev, 1) if prev else None,
        "eventos_codigo_azul_30d": int(consumo["eventos30"]),
    }


def kpis_analiticos() -> dict:
    bajas = leer_gold("bajas_mensual")
    rev = leer_gold("revisiones_mensual")
    eventos = leer_gold("eventos_mensuales")
    if bajas.empty:
        return {}
    hace12 = pd.Timestamp(date.today()) - pd.DateOffset(months=12)
    b12 = bajas[pd.to_datetime(bajas["mes"]) >= hace12]
    r = rev.copy(); r["mes"] = pd.to_datetime(r["mes"])
    ult_mes = r["mes"].max()
    e = eventos.copy(); e["mes"] = pd.to_datetime(e["mes"])
    e12 = e[e["mes"] >= hace12]["eventos_codigo_azul"].sum()
    e_prev = e[(e["mes"] < hace12) & (e["mes"] >= hace12 - pd.DateOffset(months=12))]["eventos_codigo_azul"].sum()
    return {
        "perdida_vencimiento_12m": float(b12["costo"].sum()),
        "unidades_vencidas_12m": int(b12["unidades"].sum()),
        "cumplimiento_revision_pct": round(float(r[r["mes"] == ult_mes]["cumplimiento_pct"].mean()), 1),
        "discrepancias_ultimo_mes": int(r[r["mes"] == ult_mes]["discrepancias"].sum()),
        "eventos_codigo_azul_12m": int(e12),
        "variacion_eventos_anual_pct": float(round(100 * (e12 - e_prev) / e_prev, 1)) if e_prev else None,
    }
