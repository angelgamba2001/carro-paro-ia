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


@herramienta("detalle_carro", "Estado completo de un carro: qué falta, qué vence, cuánto se consumió "
             "y qué alertas tiene abiertas.", "inventario.ver",
             {"type": "object", "required": ["carro"],
              "properties": {"carro": {"type": "string", "description": "Código, p. ej. CP-URG-01"}}})
def detalle_carro(usuario, carro: str):
    carro = (carro or "").strip().upper()
    stock = srv_inv.stock_por_carro(usuario)
    stock = stock[stock["carro"] == carro]
    if stock.empty:
        disponibles = sorted(srv_inv.stock_por_carro(usuario)["carro"].unique())
        return {"error": f"No existe el carro {carro}.", "carros_disponibles": disponibles}
    inv = srv_inv.listar_inventario(usuario, carro_id=int(stock["carro_id"].iloc[0]))
    faltan = stock[stock["stock"] < stock["stock_minimo"]]
    alertas_carro = srv_alertas.listar_alertas(usuario, solo_pendientes=True,
                                               carro_id=int(stock["carro_id"].iloc[0]))
    return {
        "carro": carro,
        "servicio": stock["servicio"].iloc[0],
        "medicamentos_bajo_minimo": len(faltan),
        "criticos_bajo_minimo": int((faltan["criticidad"] == "ALTA").sum()),
        "faltantes": faltan[["medicamento", "criticidad", "stock", "stock_minimo"]],
        "unidades_totales": int(inv["cantidad"].sum()) if not inv.empty else 0,
        "lotes_vencidos": int((inv["estado"] == "vencido").sum()) if not inv.empty else 0,
        "lotes_por_vencer": int((inv["estado"] == "proximo_a_vencer").sum()) if not inv.empty else 0,
        "proximos_vencimientos": (inv[inv["dias_para_vencer"] <= 60]
                                  [["medicamento", "lote", "cantidad", "dias_para_vencer"]]
                                  .sort_values("dias_para_vencer").head(8) if not inv.empty else []),
        "alertas_pendientes": len(alertas_carro),
    }


@herramienta("comparar_servicios", "Compara los servicios entre sí: faltantes, unidades vencidas, "
             "consumo y combinaciones en riesgo. Útil para decidir por dónde empezar.", "inventario.ver")
def comparar_servicios(usuario):
    stock = srv_inv.stock_por_carro(usuario)
    inv = srv_inv.listar_inventario(usuario)
    pred = leer_gold("predicciones")
    filas = []
    for servicio, g in stock.groupby("servicio"):
        faltan = g[g["stock"] < g["stock_minimo"]]
        inv_s = inv[inv["servicio"] == servicio] if not inv.empty else inv
        en_riesgo = 0
        if not pred.empty and "servicio" in pred.columns:
            en_riesgo = int(pred[(pred["servicio"] == servicio) &
                                 (pred["riesgo_desabastecimiento"] == 1)].shape[0])
        filas.append({
            "servicio": servicio,
            "carros": int(g["carro"].nunique()),
            "faltantes": len(faltan),
            "faltantes_criticos": int((faltan["criticidad"] == "ALTA").sum()),
            "unidades_vencidas": int(inv_s[inv_s["estado"] == "vencido"]["cantidad"].sum()) if not inv_s.empty else 0,
            "unidades_por_vencer": int(inv_s[inv_s["estado"] == "proximo_a_vencer"]["cantidad"].sum()) if not inv_s.empty else 0,
            "combinaciones_en_riesgo": en_riesgo,
        })
    tabla = pd.DataFrame(filas).sort_values(["faltantes_criticos", "unidades_vencidas"], ascending=False)
    peor = tabla.iloc[0]["servicio"] if not tabla.empty else None
    return {"comparacion": tabla, "servicio_con_mas_problemas": peor}


@herramienta("buscar_medicamento", "Dónde está un medicamento: existencias por carro, lotes y "
             "vencimientos. Acepta el nombre parcial.", "inventario.ver",
             {"type": "object", "required": ["nombre"],
              "properties": {"nombre": {"type": "string", "description": "Nombre o parte, p. ej. adrenalina"}}})
def buscar_medicamento(usuario, nombre: str):
    texto = (nombre or "").strip().lower()
    if len(texto) < 3:
        return {"error": "Indique al menos tres letras del nombre."}
    stock = srv_inv.stock_por_carro(usuario)
    coincide = stock[stock["medicamento"].str.lower().str.contains(texto, regex=False)]
    if coincide.empty:
        return {"error": f"Ningún medicamento del catálogo coincide con '{nombre}'."}
    nombres = sorted(coincide["medicamento"].unique())
    inv = srv_inv.listar_inventario(usuario)
    lotes = inv[inv["medicamento"].isin(nombres)] if not inv.empty else inv
    return {
        "coincidencias": nombres,
        "existencias": coincide[["carro", "servicio", "medicamento", "stock", "stock_minimo"]]
                       .sort_values("stock"),
        "total_unidades": int(coincide["stock"].sum()),
        "carros_sin_existencias": coincide[coincide["stock"] == 0]["carro"].tolist(),
        "lotes": (lotes[["carro", "lote", "cantidad", "fecha_vencimiento", "estado"]]
                  .sort_values("fecha_vencimiento").head(15) if not lotes.empty else []),
    }


@herramienta("orden_reposicion", "Pedido consolidado para farmacia: cuántas unidades de cada "
             "medicamento hay que pedir en total y cuánto costaría.", "inventario.ver",
             {"type": "object", "properties": {"servicio": {"type": "string"}}})
def orden_reposicion(usuario, servicio: str | None = None):
    stock = srv_inv.stock_por_carro(usuario)
    if servicio:
        stock = stock[stock["servicio"].str.lower() == servicio.strip().lower()]
        if stock.empty:
            return {"error": f"No hay carros en el servicio '{servicio}'."}
    pred = leer_gold("predicciones")
    if not pred.empty:
        stock = stock.merge(pred[["carro", "medicamento", "demanda_estimada"]],
                            on=["carro", "medicamento"], how="left")
    else:
        stock["demanda_estimada"] = 0.0
    stock["demanda_estimada"] = stock["demanda_estimada"].fillna(0)
    stock["faltan"] = (stock["stock_maximo"] - stock["stock"] +
                       stock["demanda_estimada"].round()).clip(lower=0)
    pedir = stock[stock["faltan"] > 0]
    if pedir.empty:
        return {"aviso": "Ningún carro necesita reposición en este momento."}
    consolidado = (pedir.groupby(["medicamento", "criticidad"], as_index=False)
                        .agg(unidades=("faltan", "sum"), carros=("carro", "nunique"),
                             costo_unitario=("costo_unitario", "first")))
    consolidado["unidades"] = consolidado["unidades"].astype(int)
    consolidado["costo"] = consolidado["unidades"] * consolidado["costo_unitario"]
    orden = {"ALTA": 0, "MEDIA": 1, "BAJA": 2}
    consolidado = consolidado.assign(_o=consolidado["criticidad"].map(orden)).sort_values(
        ["_o", "costo"], ascending=[True, False]).drop(columns="_o")
    return {"pedido": consolidado[["medicamento", "criticidad", "unidades", "carros", "costo"]],
            "lineas": len(consolidado),
            "unidades_totales": int(consolidado["unidades"].sum()),
            "costo_total": float(consolidado["costo"].sum())}


@herramienta("historial_consumo", "Cómo ha evolucionado el consumo de un medicamento en los últimos "
             "meses, por servicio.", "dashboard.analitico",
             {"type": "object", "properties": {"medicamento": {"type": "string"},
                                               "meses": {"type": "integer", "default": 12}}})
def historial_consumo(usuario, medicamento: str | None = None, meses: int = 12):
    df = leer_gold("consumo_mensual_servicio")
    if df.empty:
        return {"aviso": "Todavía no hay histórico procesado."}
    df = df.copy()
    df["mes"] = pd.to_datetime(df["mes"])
    limite = df["mes"].max() - pd.DateOffset(months=int(meses))
    df = df[df["mes"] > limite]
    if medicamento:
        texto = medicamento.strip().lower()
        df = df[df["medicamento"].str.lower().str.contains(texto, regex=False)]
        if df.empty:
            return {"error": f"Sin consumo registrado para '{medicamento}' en el periodo."}
    resumen = (df.groupby(df["mes"].dt.strftime("%Y-%m"), as_index=False)["unidades"].sum()
                 .rename(columns={"mes": "periodo"}))
    por_servicio = df.groupby("servicio", as_index=False)["unidades"].sum().sort_values(
        "unidades", ascending=False)
    mitad = len(resumen) // 2 or 1
    previo = resumen["unidades"].head(mitad).mean()
    reciente = resumen["unidades"].tail(mitad).mean()
    tendencia = "estable"
    if previo:
        cambio = (reciente - previo) / previo * 100
        tendencia = ("al alza" if cambio > 12 else "a la baja" if cambio < -12 else "estable")
    return {"medicamento": medicamento or "todos", "meses": int(meses),
            "por_mes": resumen, "por_servicio": por_servicio,
            "total_unidades": int(df["unidades"].sum()), "tendencia": tendencia}


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


@herramienta("atender_alerta", "Marca una alerta como atendida dejando constancia de quién lo hizo "
             "y por qué. Pida siempre el número de alerta antes de usarla.", "alertas.gestionar",
             {"type": "object", "required": ["alerta_id", "nota"],
              "properties": {"alerta_id": {"type": "integer"},
                             "nota": {"type": "string", "description": "Acción realizada"}}},
             es_accion=True)
def atender_alerta(usuario, alerta_id: int, nota: str):
    from src.servicios.errores import ErrorNegocio
    try:
        srv_alertas.atender_alerta(usuario, int(alerta_id), nota, origen_llamada="AGENTE")
        return {"atendida": True, "alerta_id": int(alerta_id)}
    except ErrorNegocio as e:
        return {"atendida": False, "error": str(e)}
