"""
Demostración rápida por consola de los componentes del proyecto (para la sustentación).
Requiere haber ejecutado: inicializar_bd.py, generar_historico.py y ejecutar_pipeline.py
"""
from src.agente.agente import AgenteCarroParo
from src.analitica.kpis import kpis_analiticos, kpis_operativos
from src.analitica.prediccion import leer_metricas
from src.bigdata.procesamiento import ultima_ejecucion
from src.database.connection import consultar
from src.ocr.extractor_fechas import extraer_fecha_texto
from src.seguridad.autenticacion import autenticar

L = "=" * 70
print(L, "\nSMARTDATA 360 · CARRO DE PARO — DEMOSTRACIÓN\n", L, sep="")

tablas = consultar("SELECT table_name AS t, table_rows AS n FROM information_schema.tables "
                   "WHERE table_schema = DATABASE() ORDER BY table_name")
print("\n[1] Base de datos:", ", ".join(f"{x['t']}({x['n']})" for x in tablas))

r = autenticar("regente@hospital.com", "Carro#Paro2026")
print("\n[2] Seguridad: login regente ->", "OK" if r.ok else r.mensaje, "| rol:", r.usuario and r.usuario["rol"])

e = ultima_ejecucion()
print("\n[3] Big Data:", e and f"motor {e['motor']}, {sum(e['silver_filas'].values()):,} registros limpios, "
                             f"{e['descartadas_limpieza']} descartados")
m = leer_metricas()
print("\n[4] Analítica: MAE modelo", m and m["mae_modelo"], "vs línea base", m and m["mae_linea_base"])
print("    KPI operativos:", kpis_operativos())
print("    KPI históricos:", kpis_analiticos())

print("\n[5] OCR: 'LOT B8942 VENC 12/05/2027' ->", extraer_fecha_texto("LOT B8942 VENC 12/05/2027"))

if r.ok:
    res = AgenteCarroParo().responder(r.usuario, "¿Hay riesgo de desabastecimiento y qué debo reponer?")
    print("\n[6] Agente IA (herramientas:", ", ".join(res["herramientas_usadas"]), ")\n", res["respuesta"][:800])
print(L)
