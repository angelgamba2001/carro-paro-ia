"""
Proveedores de razonamiento del agente.

  llm          -> LLM real con tool-calling (Ollama local, Hugging Face, Groq...).
  reglas       -> funciona sin conexión ni costo. Enruta la pregunta a herramientas por
                  palabras clave y redacta la respuesta con plantillas. Sirve para la
                  demostración y como respaldo si el LLM no responde.
  huggingface  -> ESPACIO PARA INTEGRAR un LLM de Hugging Face con tool-calling.
  anthropic    -> ESPACIO PARA INTEGRAR Claude vía API con tool-calling.

Todos implementan la misma interfaz, así que cambiar de proveedor es cambiar
AGENTE_PROVEEDOR en el .env; el resto del agente (herramientas, permisos,
auditoría) no se toca.
"""
import json
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src import config
from src.agente.prompts import PROMPT_SISTEMA


@dataclass
class Paso:
    """Lo que el proveedor decide en cada vuelta del ciclo del agente."""
    llamadas: list[tuple[str, dict]] = field(default_factory=list)   # [(herramienta, argumentos)]
    respuesta: str | None = None                                     # respuesta final


class ProveedorLLM(ABC):
    nombre = "base"

    @abstractmethod
    def siguiente_paso(self, pregunta: str, resultados: list[dict], herramientas: list) -> Paso:
        """pregunta: texto del usuario. resultados: [{'herramienta', 'argumentos', 'resultado'}] ya ejecutados.
        herramientas: lista de Herramienta permitidas para el usuario."""


# ---------------------------------------------------------------------------
# Proveedor por reglas (operativo)
# ---------------------------------------------------------------------------
def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()


_INTENCIONES = [
    (("compar", "cual servicio", "que servicio", "peor servicio", "mejor servicio"), "comparar_servicios"),
    (("detalle", "estado del carro", "como esta el carro", "como va el carro", "revisa el carro"), "detalle_carro"),
    (("busca", "buscar", "donde hay", "donde esta", "en que carro", "quedan"), "buscar_medicamento"),
    (("pedido", "orden de compra", "orden de repos", "cuanto cuesta repon", "consolidad"), "orden_reposicion"),
    (("historial", "evolucion", "ultimos meses", "tendencia de consumo", "se consume mas"), "historial_consumo"),
    (("venc", "caduc", "expir"), "consultar_vencimientos"),
    (("stock", "falta", "faltante", "minimo", "incomplet"), "consultar_stock_bajo"),
    (("alerta", "pendiente"), "listar_alertas_pendientes"),
    (("predic", "desabast", "demanda", "proxima semana", "cobertura", "alcanza"), "predecir_desabastecimiento"),
    (("anomal", "raro", "inusual", "sospech"), "consultar_anomalias"),
    (("perdida", "historic", "tendencia", "cumplimiento", "revision", "codigo azul"), "indicadores_historicos"),
    (("riesgo",), "matriz_riesgo"),
    (("repon", "comprar", "reposicion", "recomend"), "recomendar_reposicion"),
    (("resumen", "estado general", "como esta", "kpi", "indicador"), "resumen_inventario"),
]


def _cop(v) -> str:
    return f"${v:,.0f}".replace(",", ".")


def _redactar(r: dict) -> str:
    nombre, res = r["herramienta"], r["resultado"]
    if isinstance(res, dict) and res.get("error"):
        return f"• No pude consultar {nombre}: {res['error']}"
    if nombre == "resumen_inventario":
        return (f"• Inventario: {res['unidades']} unidades; {res['unidades_vencidas']} vencidas y "
                f"{res['unidades_proximas']} próximas a vencer (valor en riesgo {_cop(res['valor_en_riesgo'])}). "
                f"Carros completos: {res['carros_completos']}/{res['total_carros']}. "
                f"Alertas pendientes: {res['alertas_pendientes']} ({res['alertas_altas']} de severidad alta).")
    if nombre == "consultar_vencimientos":
        if not res:
            return "• No hay lotes vencidos ni por vencer en ese plazo."
        vencidos = [x for x in res if x["dias_para_vencer"] < 0]
        lineas = [f"   - {x['carro']}: {x['medicamento']} lote {x['lote']} ({x['cantidad']} ud), "
                  f"{'VENCIDO' if x['dias_para_vencer'] < 0 else 'vence en ' + str(x['dias_para_vencer']) + ' días'}"
                  for x in res[:8]]
        return f"• {len(res)} lotes vencidos o por vencer ({len(vencidos)} ya vencidos). Los más urgentes:\n" + \
            "\n".join(lineas)
    if nombre == "consultar_stock_bajo":
        if not res:
            return "• Todos los carros cumplen el stock mínimo."
        altas = [x for x in res if x["criticidad"] == "ALTA"]
        lineas = [f"   - {x['carro']}: {x['medicamento']} {x['stock']}/{x['stock_minimo']}" for x in res[:8]]
        return f"• {len(res)} faltantes bajo el mínimo ({len(altas)} de criticidad ALTA):\n" + "\n".join(lineas)
    if nombre == "listar_alertas_pendientes":
        lineas = [f"   - [{a['severidad']}] {a['tipo']}: {a['mensaje']}" for a in res["alertas"][:8]]
        return f"• {res['total']} alertas pendientes. Las primeras:\n" + "\n".join(lineas)
    if nombre == "predecir_desabastecimiento":
        if "aviso" in res:
            return "• " + res["aviso"]
        lineas = [f"   - {x['carro']}: {x['medicamento']} — stock {x['stock']}, demanda prevista "
                  f"{x['demanda_estimada']:.1f}, cobertura {x['dias_cobertura']:.0f} días, reponer "
                  f"{x['unidades_a_reponer']}" for x in res["detalle"]]
        return (f"• Según el modelo, {res['total_en_riesgo']} combinaciones carro-medicamento quedarían bajo el "
                f"mínimo en {res['horizonte_dias']} días:\n" + "\n".join(lineas))
    if nombre == "consultar_anomalias":
        if not res:
            return "• No se detectaron consumos anómalos en las últimas semanas."
        return "• Consumos anómalos:\n" + "\n".join(
            f"   - {x['carro']}: {x['medicamento']} — {x['motivo']}" for x in res[:8])
    if nombre == "indicadores_historicos":
        if not res:
            return "• El histórico aún no se ha procesado."
        var = res.get("variacion_eventos_anual_pct")
        return (f"• Últimos 12 meses: pérdidas por vencimiento {_cop(res['perdida_vencimiento_12m'])} "
                f"({res['unidades_vencidas_12m']} ud); {res['eventos_codigo_azul_12m']} códigos azules"
                f"{f' ({var:+.1f}% vs año anterior)' if var is not None else ''}. Cumplimiento de revisión "
                f"diaria el último mes: {res['cumplimiento_revision_pct']}% con {res['discrepancias_ultimo_mes']} "
                f"discrepancias de conteo.")
    if nombre == "matriz_riesgo":
        if not res:
            return "• No hay combinaciones en ese nivel de riesgo."
        return f"• {len(res)} combinaciones en riesgo ALTO. Las principales:\n" + "\n".join(
            f"   - {x['carro']}: {x['medicamento']} (puntaje {x['puntaje_riesgo']}: {x['justificacion']})"
            for x in res[:8])
    if nombre == "detalle_carro":
        if res.get("error"):
            return f"• {res['error']} Carros disponibles: {', '.join(res.get('carros_disponibles', []))}"
        lineas = [f"• {res['carro']} ({res['servicio']}): {res['unidades_totales']} unidades, "
                  f"{res['medicamentos_bajo_minimo']} medicamentos bajo el mínimo "
                  f"({res['criticos_bajo_minimo']} críticos), {res['lotes_vencidos']} lotes vencidos y "
                  f"{res['lotes_por_vencer']} por vencer. Alertas abiertas: {res['alertas_pendientes']}."]
        for x in res.get("faltantes", [])[:6]:
            lineas.append(f"   - falta {x['medicamento']} ({x['criticidad']}): {x['stock']} de {x['stock_minimo']}")
        return "\n".join(lineas)
    if nombre == "comparar_servicios":
        filas = res["comparacion"]
        lineas = [f"   - {x['servicio']}: {x['faltantes']} faltantes ({x['faltantes_criticos']} críticos), "
                  f"{x['unidades_vencidas']} ud vencidas, {x['combinaciones_en_riesgo']} en riesgo"
                  for x in filas]
        return (f"• Comparación por servicio (el más comprometido es {res['servicio_con_mas_problemas']}):\n"
                + "\n".join(lineas))
    if nombre == "buscar_medicamento":
        if res.get("error"):
            return f"• {res['error']}"
        sin = res["carros_sin_existencias"]
        lineas = [f"   - {x['carro']}: {x['stock']} de {x['stock_minimo']} mínimas"
                  for x in res["existencias"][:8]]
        return (f"• {', '.join(res['coincidencias'])}: {res['total_unidades']} unidades en total"
                + (f", sin existencias en {', '.join(sin)}" if sin else "") + ".\n" + "\n".join(lineas))
    if nombre == "orden_reposicion":
        if res.get("aviso"):
            return "• " + res["aviso"]
        if res.get("error"):
            return "• " + res["error"]
        lineas = [f"   - {x['medicamento']} ({x['criticidad']}): {x['unidades']} ud para "
                  f"{x['carros']} carros, {_cop(x['costo'])}" for x in res["pedido"][:10]]
        return (f"• Pedido consolidado: {res['lineas']} medicamentos, {res['unidades_totales']} unidades, "
                f"{_cop(res['costo_total'])} en total.\n" + "\n".join(lineas))
    if nombre == "historial_consumo":
        if res.get("aviso") or res.get("error"):
            return "• " + (res.get("aviso") or res["error"])
        top = res["por_servicio"][:3]
        return (f"• {res['medicamento']} en los últimos {res['meses']} meses: "
                f"{res['total_unidades']} unidades, tendencia {res['tendencia']}. "
                f"Mayor consumo en " + ", ".join(f"{x['servicio']} ({int(x['unidades'])})" for x in top) + ".")
    if nombre == "atender_alerta":
        return ("• Alerta #{} marcada como atendida.".format(res["alerta_id"]) if res.get("atendida")
                else f"• No se pudo atender la alerta: {res.get('error', 'error desconocido')}")
    if nombre == "recomendar_reposicion":
        items = res["items"]
        if not items:
            return "• No se requiere reposición en este momento."
        lineas = [f"   - {x['carro']}: {x['medicamento']} x{int(x['reponer'])}" for x in items[:12]]
        return (f"• Reposición sugerida ({len(items)} ítems, costo estimado {_cop(res['costo_total'])}):\n"
                + "\n".join(lineas))
    return f"• {nombre}: {res}"


def _medicamento_mencionado(texto: str) -> str | None:
    """Busca en la pregunta el nombre de un medicamento del catálogo.
    Compara por la primera palabra (el principio activo), que es como la gente los nombra."""
    try:
        from src.servicios.catalogo import listar_medicamentos
        for m in listar_medicamentos():
            clave = _norm(m["nombre"].split()[0])
            if len(clave) >= 5 and clave in texto:
                return m["nombre"]
    except Exception:
        pass
    return None


class ProveedorReglas(ProveedorLLM):
    nombre = "reglas"

    def siguiente_paso(self, pregunta, resultados, herramientas):
        disponibles = {h.nombre for h in herramientas}
        if not resultados:
            texto = _norm(pregunta)
            detectadas = [h for claves, h in _INTENCIONES if any(c in texto for c in claves)]
            elegidas = [h for h in detectadas if h in disponibles]
            self.denegadas = [h for h in dict.fromkeys(detectadas) if h not in disponibles]
            if not elegidas:
                elegidas = [h for h in ("resumen_inventario", "listar_alertas_pendientes") if h in disponibles]
            if not elegidas:
                return Paso(respuesta="No tengo herramientas autorizadas para su rol que respondan esa pregunta.")
            args = {}
            m = re.search(r"cp-[a-z]+-\d+", texto)
            if m:
                args["carro"] = m.group(0).upper()
            medicamento = _medicamento_mencionado(texto)
            if medicamento:
                args["nombre"] = medicamento          # buscar_medicamento
                args["medicamento"] = medicamento     # historial_consumo
            for servicio in ("urgencias", "uci adultos", "uci pediatrica", "hospitalizacion",
                             "cirugia", "pediatria"):
                if servicio in texto:
                    args["servicio"] = servicio.title().replace("Uci", "UCI")
                    break
            llamadas = []
            for h in dict.fromkeys(elegidas):
                parametros = next(x for x in herramientas if x.nombre == h).parametros
                esperados = parametros.get("properties", {})
                requeridos = parametros.get("required", [])
                h_args = {k: v for k, v in args.items() if k in esperados}
                if any(r not in h_args for r in requeridos):
                    continue           # sin el dato obligatorio, la herramienta no se invoca
                llamadas.append((h, h_args))
            if not llamadas:
                return Paso(respuesta="Para responder eso necesito el dato concreto: indique el carro "
                                      "(por ejemplo CP-URG-01) o el nombre del medicamento.")
            return Paso(llamadas=llamadas)
        cuerpo = "\n".join(_redactar(r) for r in resultados)
        denegadas = getattr(self, "denegadas", [])
        if denegadas:
            cuerpo = (f"Su rol no tiene acceso a: {', '.join(denegadas)}. Le muestro lo que sí puedo consultar.\n"
                      + cuerpo)
        return Paso(respuesta=cuerpo + "\n\n_Respuesta generada por el motor de reglas a partir de los datos del "
                                       "sistema._")


# ---------------------------------------------------------------------------
# ESPACIOS PARA INTEGRAR UN LLM
# ---------------------------------------------------------------------------
class ProveedorHuggingFace(ProveedorLLM):
    """
    TODO (integración LLM): implementar con huggingface_hub.InferenceClient y un modelo con
    soporte de tool-calling. Pasos:
      1. pip install huggingface_hub ; definir HF_TOKEN y HF_MODELO en .env
      2. cliente = InferenceClient(model=config.HF_MODELO, token=config.HF_TOKEN)
      3. Construir mensajes: [{"role":"system","content":PROMPT_SISTEMA}, {"role":"user","content":pregunta}]
         + los resultados previos como mensajes de rol "tool".
      4. Enviar las herramientas con esquemas_llm(usuario, formato="openai").
      5. Si la respuesta trae tool_calls -> Paso(llamadas=[(nombre, json.loads(argumentos)), ...])
         si no -> Paso(respuesta=texto).
    Mientras no esté implementado, el agente usa ProveedorReglas como respaldo.
    """
    nombre = "huggingface"

    def siguiente_paso(self, pregunta, resultados, herramientas):
        raise NotImplementedError("Proveedor Hugging Face pendiente de integrar")


class ProveedorAnthropic(ProveedorLLM):
    """
    TODO (integración LLM): implementar con el SDK `anthropic` (messages.create con tools=...).
    Usar esquemas_llm(usuario, formato="anthropic"), PROMPT_SISTEMA como system y devolver
    los bloques tool_use como Paso(llamadas=...). Los resultados vuelven como bloques tool_result.
    """
    nombre = "anthropic"

    def siguiente_paso(self, pregunta, resultados, herramientas):
        raise NotImplementedError("Proveedor Anthropic pendiente de integrar")


class ProveedorOpenAICompatible(ProveedorLLM):
    """
    LLM con tool-calling mediante la API compatible con OpenAI (/v1/chat/completions).
    Sirve para Ollama (modelo local: los datos no salen del equipo), Hugging Face
    (https://router.huggingface.co/v1), Groq y servicios similares. Se configura con
    LLM_URL, LLM_MODELO y LLM_API_KEY en el .env.
    """

    def __init__(self):
        self.url = config.LLM_URL.rstrip("/") + "/chat/completions"
        self.modelo = config.LLM_MODELO
        self.cabeceras = {"Authorization": f"Bearer {config.LLM_API_KEY}"} if config.LLM_API_KEY else {}
        self.nombre = f"llm:{self.modelo}"

    @staticmethod
    def _mensajes(pregunta, resultados):
        msgs = [{"role": "system", "content": PROMPT_SISTEMA},
                {"role": "user", "content": pregunta}]
        for i, r in enumerate(resultados):
            cid = f"call_{i}"
            msgs.append({"role": "assistant", "content": "", "tool_calls": [{
                "id": cid, "type": "function",
                "function": {"name": r["herramienta"],
                             "arguments": json.dumps(r["argumentos"], ensure_ascii=False)}}]})
            datos = json.dumps(r["resultado"], ensure_ascii=False, default=str)
            msgs.append({"role": "tool", "tool_call_id": cid, "content": datos[:12000]})
        return msgs

    def siguiente_paso(self, pregunta, resultados, herramientas):
        import httpx
        cuerpo = {"model": self.modelo, "temperature": 0.2, "stream": False,
                  "messages": self._mensajes(pregunta, resultados)}
        # Después de varias consultas se retiran las herramientas para obligarlo a responder
        if herramientas and len(resultados) < 6:
            cuerpo["tools"] = [{"type": "function", "function": {
                "name": h.nombre, "description": h.descripcion, "parameters": h.parametros}}
                for h in herramientas]
        r = httpx.post(self.url, json=cuerpo, headers=self.cabeceras, timeout=config.LLM_TIMEOUT)
        r.raise_for_status()
        msg = r.json()["choices"][0]["message"]
        llamadas = []
        for tc in msg.get("tool_calls") or []:
            args = tc["function"].get("arguments") or "{}"
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            llamadas.append((tc["function"]["name"], args or {}))
        if llamadas:
            return Paso(llamadas=llamadas)
        return Paso(respuesta=(msg.get("content") or "").strip() or "El modelo no generó respuesta.")


def obtener_proveedor() -> ProveedorLLM:
    return {"llm": ProveedorOpenAICompatible,
            "huggingface": ProveedorHuggingFace,
            "anthropic": ProveedorAnthropic}.get(config.AGENTE_PROVEEDOR, ProveedorReglas)()


_ = PROMPT_SISTEMA  # lo usan los proveedores LLM al integrarse
