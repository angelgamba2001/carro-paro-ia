"""
Acceso al asistente desde cualquier pantalla.

Streamlit no admite elementos fijos en la esquina por sus propios medios: cada
componente vive dentro del flujo del documento. La solución es anclar por CSS el
contenedor del popover, identificado por una clave que solo usa este componente.
"""
import streamlit as st

from app.componentes import accion
from src.agente.agente import AgenteCarroParo
from src.agente.herramientas import herramientas_permitidas
from src.seguridad.permisos import tiene_permiso

CLAVE = "burbuja_agente"

CSS = """
<style>
/* Ancla el popover del asistente a la esquina inferior derecha */
.stApp [class*="st-key-burbuja_agente"] {
  position: fixed; right: 1.6rem; bottom: 1.6rem; z-index: 999; width: auto;
}
.stApp [class*="st-key-burbuja_agente"] [data-testid="stPopoverButton"] {
  border-radius: 999px; padding: .62rem 1.25rem; width: auto; min-width: 0;
  background: var(--carro); color: #fff; border: 1px solid var(--carro);
  box-shadow: 0 2px 10px rgba(18,23,28,.18); font-weight: 500;
  transition: background .15s ease, transform .15s ease;
}
.stApp [class*="st-key-burbuja_agente"] [data-testid="stPopoverButton"]:hover {
  background: var(--carro-hundido); border-color: var(--carro-hundido);
  color: #fff; transform: translateY(-1px);
}
.burbuja-cabecera {
  display: flex; align-items: baseline; justify-content: space-between;
  border-bottom: 1px solid var(--linea); padding-bottom: .4rem; margin-bottom: .6rem;
}
.burbuja-cabecera b { font-size: .95rem; }
.burbuja-cabecera span { font-size: .74rem; color: var(--acero); }
.burbuja-cabecera span b { font-family: var(--mono); font-variant-numeric: tabular-nums;
                           font-weight: 500; font-size: .74rem; color: var(--tinta-suave); }
/* La respuesta se distingue por su propia superficie, no por una franja de color */
.burbuja-respuesta {
  font-size: .9rem; line-height: 1.6; background: var(--papel-hundido);
  border-top: 1px solid var(--monitor);
  padding: .6rem .7rem; margin: .5rem 0 .2rem; white-space: pre-wrap;
}
@media (max-width: 820px) { .stApp [class*="st-key-burbuja_agente"] { right: .8rem; bottom: .8rem; } }
</style>
"""

ATAJOS = {
    "Estado general": "Dame un resumen del estado de los carros",
    "Faltantes críticos": "¿Qué carros tienen medicamentos críticos bajo el mínimo?",
    "Vencimientos": "¿Qué medicamentos vencen en los próximos 30 días?",
    "Qué pedir": "Dame la orden de reposición consolidada",
}


def mostrar(usuario: dict):
    """Dibuja la burbuja. No hace nada si el rol no puede usar el asistente."""
    if not tiene_permiso(usuario, "agente.usar"):
        return
    st.markdown(CSS, unsafe_allow_html=True)

    with st.container(key=CLAVE):
        with st.popover("Preguntar al asistente", width=420):
            _panel(usuario)


def _panel(usuario: dict):
    n = len(herramientas_permitidas(usuario))
    st.markdown(f'<div class="burbuja-cabecera"><b>Asistente</b>'
                f'<span><b>{n}</b> herramientas</span></div>', unsafe_allow_html=True)

    columnas = st.columns(2)
    elegido = None
    for i, (etiqueta, consulta) in enumerate(ATAJOS.items()):
        if columnas[i % 2].button(etiqueta, key=f"atajo_{i}", width="stretch"):
            elegido = consulta

    escrito = st.chat_input("Escriba su pregunta", key="burbuja_entrada")
    pregunta = escrito or elegido

    if pregunta:
        with st.spinner("Consultando…"):
            r = accion(AgenteCarroParo().responder, usuario, pregunta)
        if r:
            texto = r["respuesta"].split("\n\n_Respuesta generada")[0]
            st.session_state["burbuja_ultima"] = (pregunta, texto, r["herramientas_usadas"])

    ultima = st.session_state.get("burbuja_ultima")
    if ultima:
        pregunta, respuesta, usadas = ultima
        st.caption(f"Usted preguntó: {pregunta}")
        st.markdown(f'<div class="burbuja-respuesta">{respuesta}</div>', unsafe_allow_html=True)
        if usadas:
            st.caption("Consultó: " + ", ".join(usadas))
        if st.button("Abrir el asistente completo", width="stretch"):
            st.session_state["ir_a_agente"] = True
            st.rerun()
