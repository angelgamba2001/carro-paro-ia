import pandas as pd
import streamlit as st

from app.componentes import accion, cabecera
from src import config
from src.analitica.prediccion import leer_metricas
from src.bigdata.orquestador import ejecutar_flujo_completo
from src.bigdata.procesamiento import leer_gold, ultima_ejecucion

FLUJO = """
Fuentes                    Zona RAW            BRONZE          SILVER                    GOLD                 Uso
───────                    ────────            ──────          ──────                    ────                 ───
MySQL operativo  ─┐
Histórico legado ─┼──▶  CSV / JSON  ──▶  + linaje  ──▶  limpieza, tipos,  ──▶  agregados diarios,  ──▶  Dashboard
API datos.gov.co ─┘      (particionado)     (Parquet)     normalización,         semanales, mensuales      Agente IA
 (CUM)                                                    integración            calidad, riesgo           Alertas / API
                                   motor: PySpark (respaldo pandas)   ▲ predicción · anomalías · matriz de riesgo
"""


def _tamano(ruta) -> str:
    archivos = [p for p in ruta.rglob("*") if p.is_file()] if ruta.exists() else []
    return f"{len(archivos)} archivos · {sum(a.stat().st_size for a in archivos) / 1e6:.1f} MB"


def mostrar(usuario: dict):
    cabecera("Big Data", "Ingesta, procesamiento y analítica")
    st.code(FLUJO, language=None)

    c = st.columns(4)
    for col, (nombre, ruta) in zip(c, [("RAW", config.RAW_DIR), ("BRONZE", config.BRONZE_DIR),
                                       ("SILVER", config.SILVER_DIR), ("GOLD", config.GOLD_DIR)]):
        col.metric(nombre, _tamano(ruta))

    izq, der = st.columns([1, 2])
    with izq:
        motor = st.radio("Motor de procesamiento", ["spark", "pandas"],
                         index=0 if config.MOTOR_BIGDATA == "spark" else 1, horizontal=True)
        st.caption("Spark requiere Java 17+ instalado. Si no está disponible se usa pandas automáticamente.")
        if st.button("Ejecutar flujo completo", type="primary", width="stretch"):
            estado = st.status("Ejecutando pipeline...", expanded=True)
            r = accion(ejecutar_flujo_completo, usuario, motor, avisar=estado.write)
            if r:
                estado.update(label=f"Completado en {r['procesamiento']['segundos']} s", state="complete")
                st.json(r["analitica"], expanded=False)
            else:
                estado.update(label="Falló la ejecución", state="error")
    with der:
        ejec = ultima_ejecucion()
        if ejec:
            st.markdown(f"**Última ejecución:** {ejec['fecha'].replace('T', ' ')} · motor {ejec['motor']} · "
                        f"{ejec['segundos']} s · {ejec['descartadas_limpieza']} registros descartados en limpieza")
            filas = pd.DataFrame([{"zona": "SILVER", "tabla": k, "filas": v} for k, v in ejec["silver_filas"].items()]
                                 + [{"zona": "GOLD", "tabla": k, "filas": v} for k, v in ejec["gold_filas"].items()])
            st.dataframe(filas, hide_index=True, width="stretch")
        else:
            st.info("Aún no hay ejecuciones. Genere el histórico (scripts/generar_historico.py) y ejecute el flujo.")

    met = leer_metricas()
    if met:
        st.markdown("#### Modelo de predicción de demanda")
        c = st.columns(4)
        c[0].metric("MAE modelo", met["mae_modelo"])
        c[1].metric("MAE línea base", met["mae_linea_base"])
        c[2].metric("Mejora", f"{met['mejora_vs_base_pct']}%")
        c[3].metric("Filas de entrenamiento", f"{met['filas_entrenamiento']:,}".replace(",", "."))
        st.caption(f"{met['modelo']} · horizonte {met['horizonte_dias']} días · evaluado en "
                   f"{met['filas_prueba']:,} observaciones no vistas".replace(",", "."))
    cal = leer_gold("calidad_datos")
    if not cal.empty:
        st.markdown("#### Calidad de datos")
        st.dataframe(cal, hide_index=True, width="stretch")
