import logging

import streamlit as st

from app.componentes import accion, cabecera
from src.agente.agente import AgenteCarroParo
from src.agente.herramientas import herramientas_permitidas
from src.seguridad.permisos import tiene_permiso

log = logging.getLogger(__name__)

SUGERENCIAS = {
    "Resumen general": "Dame un resumen del estado de los carros",
    "Vencimientos 30 días": "¿Qué medicamentos vencen en los próximos 30 días?",
    "Riesgo de desabastecimiento": "¿Hay riesgo de desabastecimiento?",
    "Reposición CP-URG-01": "¿Qué debo reponer en CP-URG-01?",
    "Consumos anómalos": "¿Hay consumos anómalos?",
    "Faltantes críticos": "¿Qué carros tienen stock bajo el mínimo?",
}


def mostrar(usuario: dict):
    cabecera("Agente IA", "Consulta los servicios del sistema con los permisos de su rol")
    agente = AgenteCarroParo()
    herramientas = herramientas_permitidas(usuario)
    st.caption(f"Proveedor de razonamiento: **{agente.proveedor.nombre}**"
               + (" (motor de reglas sin LLM; configure AGENTE_PROVEEDOR=llm en el .env para usar un modelo "
                  "de lenguaje)" if agente.proveedor.nombre == "reglas" else
                  " · si el modelo no responde, el agente usa el motor de reglas"))
    st.info("**Aviso:** las respuestas de este asistente las genera una inteligencia artificial y pueden "
            "contener errores. Verifique siempre la información en el inventario antes de tomar una decisión "
            "sobre un carro de paro.", icon="⚠️")

    izq, der = st.columns([2.2, 1])
    with der:
        if tiene_permiso(usuario, "agente.acciones"):
            st.toggle("Permitir que el agente registre recomendaciones en el chat", key="agente_acciones",
                      help="Desactivado: el agente solo consulta. Activado: puede crear alertas de "
                           "recomendación si usted se lo pide.")
        consultas = [h for h in herramientas if not h.es_accion]
        acciones = [h for h in herramientas if h.es_accion]
        st.caption(f"Su rol puede usar {len(consultas)} consultas"
                   + (f" y {len(acciones)} acciones." if acciones else "."))
        with st.expander("Ver el detalle"):
            for h in consultas:
                st.markdown(f"**{h.nombre.replace('_', ' ').capitalize()}** — {h.descripcion}")
            for h in acciones:
                st.markdown(f"**{h.nombre.replace('_', ' ').capitalize()}** (acción) — {h.descripcion}")
        st.divider()
        st.markdown("##### Revisión autónoma")
        st.caption("El agente recorre todos los carros, prioriza hallazgos"
                   + (" y los registra como recomendaciones." if tiene_permiso(usuario, "agente.acciones")
                      else ". Su rol solo puede ver los hallazgos."))
        if st.button("Ejecutar revisión", width="stretch"):
            with st.spinner("Revisando carros..."):
                r = accion(agente.revision_autonoma, usuario)
            if r:
                if not r["hallazgos"]:
                    st.success("Sin hallazgos: todos los carros están en orden.")
                for h in r["hallazgos"]:
                    (st.error if h["prioridad"] == "ALTA" else st.warning if h["prioridad"] == "MEDIA"
                     else st.info)(h["detalle"])
                if r["recomendaciones_creadas"]:
                    st.caption(f"{len(r['recomendaciones_creadas'])} recomendaciones registradas en Alertas.")

    with izq:
        historial = st.session_state.setdefault("chat_agente", [])
        elegida = None
        cols = st.columns(3)
        for i, (etiqueta, texto) in enumerate(SUGERENCIAS.items()):
            if cols[i % 3].button(etiqueta, key=f"sug_{i}", width="stretch"):
                elegida = texto
        for m in historial:
            with st.chat_message(m["rol"]):
                st.markdown(m["texto"])
                if m.get("herramientas"):
                    st.caption("Herramientas: " + ", ".join(m["herramientas"]))
        voz_texto = _entrada_voz()
        pregunta = st.chat_input("Pregunte sobre inventario, vencimientos, riesgo o reposición") \
            or elegida or voz_texto
        if pregunta:
            historial.append({"rol": "user", "texto": pregunta})
            with st.chat_message("user"):
                st.markdown(pregunta)
            with st.chat_message("assistant"):
                with st.spinner("Consultando servicios..."):
                    r = accion(agente.responder, usuario, pregunta,
                               permitir_acciones=st.session_state.get("agente_acciones", False))
                if r:
                    st.markdown(r["respuesta"])
                    if voz_texto:
                        _leer_en_voz_alta(r["respuesta"])
                    st.caption("Herramientas: " + ", ".join(r["herramientas_usadas"]))
                    with st.expander("Ver datos consultados"):
                        st.json(r["datos"], expanded=False)
                    historial.append({"rol": "assistant", "texto": r["respuesta"],
                                      "herramientas": r["herramientas_usadas"]})
        if historial and st.button("Limpiar conversación"):
            st.session_state["chat_agente"] = []
            st.rerun()


def _entrada_voz() -> str | None:
    """Micrófono opcional: solo aparece si están instaladas faster-whisper y edge-tts."""
    from src.agente.voz import voz_disponible
    if not voz_disponible():
        return None
    audio = st.audio_input("O hable con el agente")
    if not audio:
        return None
    import hashlib
    # Bandit B324 / Semgrep hash-debil: md5 esta roto criptograficamente. La huella
    # solo evita reprocesar la misma grabacion al recargar, pero no hay ninguna razon
    # para conservar md5 cuando sha256 cuesta lo mismo aqui.
    huella = hashlib.sha256(audio.getvalue()).hexdigest()
    if st.session_state.get("ultimo_audio") == huella:   # evita repetir la misma grabación al recargar
        return None
    st.session_state["ultimo_audio"] = huella
    from src.agente.voz import transcribir
    with st.spinner("Transcribiendo audio..."):
        try:
            texto = transcribir(audio.getvalue())
        except Exception as e:
            # Antes se descartaba la excepción y solo quedaba el mensaje en pantalla:
            # sin rastro en los registros era imposible saber si falló la descarga del
            # modelo, la decodificación del audio o la memoria del contenedor.
            log.exception("Falló la transcripción del audio")
            st.error(f"No se pudo transcribir el audio — {type(e).__name__}: {e}")
            return None
    if not texto:
        st.warning("No se entendió el audio; intente de nuevo.")
        return None
    st.caption(f"Entendí: {texto}")
    return texto


def _leer_en_voz_alta(texto: str):
    from src.agente.voz import sintetizar
    try:
        st.audio(sintetizar(texto), format="audio/mp3", autoplay=True)
    except Exception as e:
        log.warning("Falló la síntesis de voz: %s: %s", type(e).__name__, e)
        st.caption("No se pudo generar el audio de la respuesta (edge-tts requiere internet).")
