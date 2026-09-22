"""Flujo completo: Fuentes -> RAW -> BRONZE/SILVER/GOLD -> Analítica -> alertas en la operación."""
from src.analitica.motor import ejecutar_analitica
from src.bigdata.ingesta import ejecutar_ingesta
from src.bigdata.procesamiento import ejecutar_procesamiento
from src.database.auditoria import registrar_log
from src.seguridad.permisos import exigir_permiso


def ejecutar_flujo_completo(usuario: dict, motor: str | None = None, origen: str = "WEB", avisar=print) -> dict:
    exigir_permiso(usuario, "bigdata.ejecutar", origen)
    avisar("1/3 Ingesta de fuentes (MySQL, histórico, datos abiertos CUM)...")
    ingesta = ejecutar_ingesta()
    avisar(f"2/3 Procesamiento Big Data (motor {motor or 'configurado'})...")
    proceso = ejecutar_procesamiento(motor)
    avisar("3/3 Analítica: predicción, anomalías y matriz de riesgo...")
    analitica = ejecutar_analitica()
    registrar_log(usuario["id"], "EJECUCION_PIPELINE", "pipeline", None,
                  f"motor={proceso['motor']} t={proceso['segundos']}s alertas_nuevas={analitica['alertas_nuevas']}",
                  origen)
    return {"ingesta": ingesta, "procesamiento": proceso, "analitica": analitica}
