"""
Asistente del tablero: responde sobre las cifras que la persona tiene en pantalla.

Tres preguntas frecuentes (resumen, prioridades y significado de los colores) se
contestan con las mismas cifras del tablero, sin depender del modelo de lenguaje: así
funcionan aunque Ollama esté apagado y nunca difieren de lo que se ve. El resto de las
preguntas pasan al agente, que recibe esas cifras como contexto y puede consultar las
herramientas que su rol permite.
"""
import unicodedata

import streamlit as st

from app import datos
from app.componentes import LEYENDA_COLORES, accion, moneda, numero
from src.seguridad.permisos import tiene_permiso

META_DISPONIBILIDAD = 90          # misma meta que usa el color de la tarjeta "Carros completos"
ATAJOS = {
    "Resumen del tablero": "resumen del tablero",
    "¿Qué atiendo primero?": "que debo atender primero",
    "¿Qué significan los colores?": "que significan los colores",
}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", (t or "").lower()).encode("ascii", "ignore").decode()


def _historicos(usuario: dict) -> dict | None:
    """Indicadores del histórico, solo si el rol ve la pestaña analítica y ya hay procesamiento."""
    if tiene_permiso(usuario, "dashboard.analitico") and datos.ejecucion_pipeline():
        return datos.kpis_historicos() or None
    return None


def resumen(k: dict, ka: dict | None = None) -> str:
    """Las cifras del tablero en lenguaje corriente."""
    disp = k["disponibilidad_pct"]
    lineas = [
        f"**Carros:** {k['carros_completos']} de {k['total_carros']} tienen completos los medicamentos "
        f"críticos ({numero(disp)} %), " + ("dentro" if disp >= META_DISPONIBILIDAD else "por debajo")
        + f" de la meta del {META_DISPONIBILIDAD} %.",
        f"**Vencimientos:** {k['unidades_vencidas']} unidades vencidas y {k['unidades_proximas']} "
        f"que vencen en los próximos 30 días. Valor en riesgo: {moneda(k['valor_en_riesgo'])}.",
        f"**Alertas:** {k['alertas_pendientes']} pendientes, {k['alertas_altas']} de severidad alta.",
        f"**Consumo (30 días):** {k['consumo_30d']} unidades"
        + (f", {numero(k['variacion_consumo_pct'], signo=True)} % frente a los 30 días previos"
           if k.get("variacion_consumo_pct") is not None else "")
        + f", con {k['eventos_codigo_azul_30d']} códigos azules.",
    ]
    if ka:
        lineas.append(
            f"**Histórico (12 meses):** pérdidas por vencimiento de {moneda(ka.get('perdida_vencimiento_12m'))} "
            f"({ka.get('unidades_vencidas_12m', 0)} unidades), {ka.get('eventos_codigo_azul_12m', 0)} códigos "
            f"azules y {numero(ka.get('cumplimiento_revision_pct'))} % de cumplimiento en la revisión diaria.")
    return "\n\n".join(lineas)


def prioridades(k: dict) -> str:
    """Qué atender primero, en orden de urgencia, a partir de las cifras del tablero."""
    pasos = []
    if k["unidades_vencidas"]:
        pasos.append(f"Retirar de los carros las **{k['unidades_vencidas']} unidades vencidas** y dar de baja sus lotes.")
    if k["disponibilidad_pct"] < META_DISPONIBILIDAD:
        faltan = k["total_carros"] - k["carros_completos"]
        pasos.append(f"Completar los medicamentos críticos de **{faltan} carros** que no los tienen completos.")
    if k["alertas_altas"]:
        pasos.append(f"Atender las **{k['alertas_altas']} alertas de severidad alta**.")
    if k["unidades_proximas"]:
        pasos.append(f"Programar la reposición de las **{k['unidades_proximas']} unidades** que vencen en 30 días.")
    if not pasos:
        return "No hay urgencias en este momento: los carros están completos y sin vencimientos."
    return "En este orden:\n\n" + "\n".join(f"{i}. {p}" for i, p in enumerate(pasos, 1))


def leyenda() -> str:
    return "\n".join(f"- **{nombre}:** {texto}." for _, nombre, texto in LEYENDA_COLORES)


def contexto(k: dict, ka: dict | None = None) -> str:
    """Cifras del tablero en texto plano para el modelo de lenguaje (datos, no instrucciones)."""
    filas = [f"carros completos: {k['carros_completos']}/{k['total_carros']} ({k['disponibilidad_pct']} %)",
             f"unidades vencidas: {k['unidades_vencidas']}",
             f"unidades próximas a vencer (30 días): {k['unidades_proximas']}",
             f"valor en riesgo: {round(k['valor_en_riesgo'])} COP",
             f"alertas pendientes: {k['alertas_pendientes']} (altas: {k['alertas_altas']})",
             f"consumo últimos 30 días: {k['consumo_30d']} unidades, variación {k.get('variacion_consumo_pct')} %, "
             f"códigos azules: {k['eventos_codigo_azul_30d']}"]
    if ka:
        filas += [f"{clave}: {valor}" for clave, valor in ka.items()]
    return "\n".join(filas)


def por_servicio(usuario: dict, texto: str) -> str | None:
    """Cifras por servicio o área (vencidas, faltantes, riesgo), calculadas sin modelo de lenguaje.

    Responde si la pregunta nombra un servicio o pide la comparación por áreas; si no, devuelve None.
    """
    if not any(c in texto for c in ("servicio", "area", "cirugia", "uci", "urgencias", "pediatria",
                                    "hospitalizacion", "perdida", "vencid", "porcentaje")):
        return None
    try:
        from src.agente.herramientas import ejecutar_herramienta
        filas = ejecutar_herramienta(usuario, "comparar_servicios").get("comparacion") or []
    except Exception:
        return None
    if not filas:
        return None
    mencionados = [f for f in filas if _norm(f["servicio"]) in texto
                   or any(len(w) > 3 and w in texto for w in _norm(f["servicio"]).split())]
    if not mencionados and not any(c in texto for c in ("servicio", "area", "compar")):
        return None
    elegidas = mencionados or filas
    lineas = [f"- **{f['servicio']}:** {f['unidades_vencidas']} de {f['unidades_total']} unidades vencidas "
              f"(**{numero(f['pct_vencido'])} %**), {f['unidades_por_vencer']} por vencer, "
              f"{f['faltantes']} faltantes ({f['faltantes_criticos']} críticos)." for f in elegidas]
    return ("Porcentaje de unidades vencidas sobre las que hay hoy en inventario, por servicio:\n\n"
            + "\n".join(lineas)
            + "\n\nEs la situación actual del inventario, no el acumulado de pérdidas de los últimos 12 meses.")


def responder(usuario: dict, pregunta: str) -> str | None:
    k = datos.kpis(usuario, datos.firma(usuario))
    texto = _norm(pregunta)
    if any(c in texto for c in ("color", "significa", "leyenda", "semaforo")):
        return leyenda()
    if any(c in texto for c in ("prioridad", "primero", "urgente", "atender", "que hago")):
        return prioridades(k)
    if tiene_permiso(usuario, "inventario.ver"):
        r = por_servicio(usuario, texto)
        if r:
            return r
    ka = _historicos(usuario)
    if any(c in texto for c in ("resumen", "estado general", "como esta", "estadistic", "indicador", "kpi",
                                "panorama", "cifras")):
        return resumen(k, ka)
    if not tiene_permiso(usuario, "agente.usar"):
        return ("Su rol puede pedir el resumen, las prioridades y el significado de los colores. "
                "Las preguntas libres requieren acceso al asistente.")
    from src.agente.agente import AgenteCarroParo
    r = accion(AgenteCarroParo().responder, usuario, pregunta[:1000], contexto=contexto(k, ka))
    return r["respuesta"].split("\n\n_Respuesta generada")[0] if r else None


@st.fragment
def mostrar(usuario: dict):
    """Panel plegable al final del tablero. Un fragmento: preguntar no vuelve a dibujar los gráficos."""
    with st.expander("Asistente del tablero · pregunte por estas cifras", expanded=False):
        columnas = st.columns(len(ATAJOS))
        elegida = None
        for col, (etiqueta, pregunta) in zip(columnas, ATAJOS.items()):
            if col.button(etiqueta, key=f"tab_bot_{etiqueta}", width="stretch"):
                elegida = pregunta
        with st.form("tab_bot_form", clear_on_submit=True, border=False):
            escrita = st.text_input("O escriba su pregunta", max_chars=300, key="tab_bot_texto",
                                    placeholder="Por ejemplo: ¿cómo va el consumo frente al mes anterior?")
            enviar = st.form_submit_button("Preguntar", type="primary")
        pregunta = elegida or (escrita.strip() if enviar and escrita.strip() else None)
        if pregunta:
            with st.spinner("Consultando las cifras…"):
                respuesta = responder(usuario, pregunta)
            if respuesta:
                st.session_state["tab_bot_ultima"] = (pregunta, respuesta)
        ultima = st.session_state.get("tab_bot_ultima")
        if ultima:
            st.caption(f"Usted preguntó: {ultima[0]}")
            st.markdown(ultima[1])
