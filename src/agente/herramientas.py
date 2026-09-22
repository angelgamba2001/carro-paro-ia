"""
Herramientas del agente IA.

El agente NO accede a la base de datos directamente: solo puede invocar estas funciones,
que a su vez usan la misma capa de servicios que la interfaz web y la API. Cada
herramienta declara el permiso que exige; el agente nunca puede hacer más que el
usuario que le pregunta (se valida en `ejecutar_herramienta`).

Para agregar una herramienta nueva basta con decorar una función con @herramienta.
Los esquemas se exportan en el formato que piden los LLM con tool-calling.
"""
import json
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

from src import config
from src.analitica.kpis import kpis_analiticos, kpis_operativos
from src.bigdata.procesamiento import leer_gold
from src.database.auditoria import registrar_log
from src.seguridad.permisos import exigir_permiso, tiene_permiso
from src.servicios import alertas as srv_alertas
from src.servicios import inventario as srv_inv


@dataclass
class Herramienta:
    nombre: str
    descripcion: str
    permiso: str
    funcion: Callable
    parametros: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
    es_accion: bool = False   # True = modifica datos (queda auditado como ACCION_AGENTE)


REGISTRO: dict[str, Herramienta] = {}


def herramienta(nombre, descripcion, permiso, parametros=None, es_accion=False):
    def decorador(fn):
        REGISTRO[nombre] = Herramienta(nombre, descripcion, permiso, fn,
                                       parametros or {"type": "object", "properties": {}}, es_accion)
        return fn
    return decorador


def herramientas_permitidas(usuario: dict) -> list[Herramienta]:
    return [h for h in REGISTRO.values() if tiene_permiso(usuario, h.permiso)]


def esquemas_llm(usuario: dict, formato: str = "anthropic") -> list[dict]:
    """Exporta las herramientas permitidas para el usuario en formato Anthropic u OpenAI/HF."""
    salida = []
    for h in herramientas_permitidas(usuario):
        if formato == "anthropic":
            salida.append({"name": h.nombre, "description": h.descripcion, "input_schema": h.parametros})
        else:
            salida.append({"type": "function", "function": {"name": h.nombre, "description": h.descripcion,
                                                            "parameters": h.parametros}})
    return salida


def _serializable(obj):
    """Convierte DataFrames (también anidados en dicts/listas) a JSON puro."""
    if isinstance(obj, pd.DataFrame):
        return json.loads(obj.to_json(orient="records", date_format="iso", force_ascii=False))
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serializable(v) for v in obj]
    return json.loads(json.dumps(obj, default=str, ensure_ascii=False))


def ejecutar_herramienta(usuario: dict, nombre: str, argumentos: dict | None = None) -> dict:
    h = REGISTRO.get(nombre)
    if not h:
        return {"error": f"Herramienta desconocida: {nombre}"}
    exigir_permiso(usuario, h.permiso, origen="AGENTE")
    try:
        resultado = h.funcion(usuario, **(argumentos or {}))
    except TypeError as e:
        return {"error": f"Argumentos inválidos para {nombre}: {e}"}
    if h.es_accion:
        registrar_log(usuario["id"], "ACCION_AGENTE", "agente", None,
                      f"{nombre}({json.dumps(argumentos or {}, ensure_ascii=False)[:300]})", "AGENTE")
    return _serializable(resultado)


# ---------------------------------------------------------------------------
# Herramientas de consulta
# ---------------------------------------------------------------------------
_P_CARRO = {"carro": {"type": "string", "description": "Código del carro, p. ej. CP-URG-01 (opcional)"}}


@herramienta("resumen_inventario", "Indicadores actuales: unidades, vencidas, próximas a vencer, valor en "
             "riesgo, carros completos, alertas pendientes y consumo de los últimos 30 días.", "inventario.ver")
def resumen_inventario(usuario):
    return kpis_operativos()


@herramienta("consultar_vencimientos", "Lotes vencidos o que vencen dentro de N días.", "inventario.ver",
             {"type": "object", "properties": {"dias": {"type": "integer", "default": 30}, **_P_CARRO}})
def consultar_vencimientos(usuario, dias: int = 30, carro: str | None = None):
    df = srv_inv.listar_inventario(usuario, estados=["vencido", "proximo_a_vencer", "vigente"])
    df = df[df["dias_para_vencer"] <= int(dias)]
    if carro:
        df = df[df["carro"] == carro.upper()]
    return df[["carro", "medicamento", "lote", "cantidad", "fecha_vencimiento", "dias_para_vencer"]].head(50)


@herramienta("consultar_stock_bajo", "Medicamentos por debajo del stock mínimo en cada carro.", "inventario.ver",
             {"type": "object", "properties": _P_CARRO})
def consultar_stock_bajo(usuario, carro: str | None = None):
    df = srv_inv.stock_por_carro(usuario)
    df = df[df["stock"] < df["stock_minimo"]]
    if carro:
        df = df[df["carro"] == carro.upper()]
    return df[["carro", "servicio", "medicamento", "criticidad", "stock", "stock_minimo"]]


@herramienta("listar_alertas_pendientes", "Alertas sin atender, ordenadas por severidad.", "alertas.ver",
             {"type": "object", "properties": {"tipo": {"type": "string", "enum": list(srv_alertas.TIPOS)},
                                               "limite": {"type": "integer", "default": 10}}})
def listar_alertas_pendientes(usuario, tipo: str | None = None, limite: int = 10):
    df = srv_alertas.listar_alertas(usuario, solo_pendientes=True, tipos=[tipo] if tipo else None)
    return {"total": len(df), "alertas": df[["id", "tipo", "severidad", "carro", "medicamento", "mensaje"]]
            .head(int(limite))}


@herramienta("predecir_desabastecimiento", "Carros y medicamentos con riesgo de desabastecimiento según el "
             "modelo de demanda, con días de cobertura y unidades sugeridas a reponer.", "dashboard.analitico",
             {"type": "object", "properties": {"limite": {"type": "integer", "default": 10}}})
def predecir_desabastecimiento(usuario, limite: int = 10):
    df = leer_gold("predicciones")
    if df.empty:
        return {"aviso": "Aún no se ha ejecutado la analítica."}
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    df = df[df["riesgo_desabastecimiento"] == 1].assign(_o=lambda d: d["criticidad"].map(orden)) \
        .sort_values(["_o", "dias_cobertura"])
    return {"horizonte_dias": config.HORIZONTE_PREDICCION_DIAS, "total_en_riesgo": len(df),
            "detalle": df[["carro", "medicamento", "criticidad", "stock", "demanda_estimada", "dias_cobertura",
                           "unidades_a_reponer"]].head(int(limite))}


@herramienta("consultar_anomalias", "Consumos anómalos detectados en las últimas semanas (Isolation Forest).",
             "dashboard.analitico")
def consultar_anomalias(usuario):
    return leer_gold("anomalias")


@herramienta("indicadores_historicos", "Indicadores del histórico procesado: pérdidas por vencimiento en 12 "
             "meses, cumplimiento de revisión diaria, discrepancias y tendencia de códigos azules.",
             "dashboard.analitico")
def indicadores_historicos(usuario):
    return kpis_analiticos()


@herramienta("matriz_riesgo", "Evaluación probabilidad x impacto por carro y medicamento.", "dashboard.analitico",
             {"type": "object", "properties": {"nivel": {"type": "string", "enum": ["ALTO", "MEDIO", "BAJO"]}}})
def matriz_riesgo(usuario, nivel: str = "ALTO"):
    df = leer_gold("riesgo")
    return df[df["nivel_riesgo"] == nivel].sort_values("puntaje_riesgo", ascending=False).head(20) \
        if not df.empty else df


@herramienta("recomendar_reposicion", "Lista de reposición sugerida por carro combinando stock mínimo, "
             "demanda prevista y lotes por vencer.", "inventario.ver", {"type": "object", "properties": _P_CARRO})
def recomendar_reposicion(usuario, carro: str | None = None):
    stock = srv_inv.stock_por_carro(usuario)
    pred = leer_gold("predicciones")
    if not pred.empty:
        stock = stock.merge(pred[["carro", "medicamento", "demanda_estimada"]], on=["carro", "medicamento"], how="left")
    else:
        stock["demanda_estimada"] = 0.0
    stock["demanda_estimada"] = stock["demanda_estimada"].fillna(0)
    stock["reponer"] = (stock["stock_maximo"] - stock["stock"] + stock["demanda_estimada"].round()).clip(lower=0)
    stock = stock[(stock["stock"] < stock["stock_minimo"]) |
                  (stock["stock"] - stock["demanda_estimada"] < stock["stock_minimo"])]
    if carro:
        stock = stock[stock["carro"] == carro.upper()]
    stock["costo_estimado"] = stock["reponer"] * stock["costo_unitario"]
    return {"items": stock[["carro", "medicamento", "criticidad", "stock", "reponer", "costo_estimado"]]
            .sort_values(["carro", "criticidad"]), "costo_total": float(stock["costo_estimado"].sum())}


# ---------------------------------------------------------------------------
# Herramientas de acción (modifican datos -> permiso específico y auditoría)
# ---------------------------------------------------------------------------
@herramienta("crear_recomendacion", "Registra una recomendación del agente como alerta para el equipo "
             "(no modifica inventario).", "agente.acciones",
             {"type": "object", "required": ["mensaje"],
              "properties": {"mensaje": {"type": "string"},
                             "severidad": {"type": "string", "enum": ["ALTA", "MEDIA", "BAJA"]}}},
             es_accion=True)
def crear_recomendacion(usuario, mensaje: str, severidad: str = "MEDIA"):
    alerta_id = srv_alertas.crear_alerta("RECOMENDACION_AGENTE", mensaje[:255], severidad, "AGENTE")
    return {"alerta_id": alerta_id, "creada": alerta_id is not None}
