"""Manejo de sesión en Streamlit: expiración por inactividad y revalidación contra la BD."""
from datetime import datetime, timedelta

import streamlit as st

from src import config
from src.database.auditoria import registrar_evento_seguridad
from src.seguridad.autenticacion import revalidar_usuario


def usuario_en_sesion() -> dict | None:
    u = st.session_state.get("usuario")
    if not u:
        return None
    ultima = st.session_state.get("ultima_actividad")
    if ultima and datetime.now() - ultima > timedelta(minutes=config.MINUTOS_INACTIVIDAD):
        registrar_evento_seguridad("SESION_EXPIRADA", u["correo"], u["id"])
        cerrar_sesion(motivo=f"La sesión expiró tras {config.MINUTOS_INACTIVIDAD} minutos de inactividad.")
        return None
    vigente = revalidar_usuario(u["id"])     # si lo desactivaron o cambiaron de rol, aplica de inmediato
    if not vigente:
        cerrar_sesion(motivo="Su cuenta fue desactivada.")
        return None
    st.session_state["usuario"] = vigente
    st.session_state["ultima_actividad"] = datetime.now()
    return vigente


def iniciar_sesion(usuario: dict):
    st.session_state.clear()
    st.session_state["usuario"] = usuario
    st.session_state["ultima_actividad"] = datetime.now()


def cerrar_sesion(motivo: str | None = None, registrar: bool = False):
    u = st.session_state.get("usuario")
    if registrar and u:
        registrar_evento_seguridad("LOGOUT", u["correo"], u["id"])
    st.session_state.clear()
    if motivo:
        st.session_state["motivo_salida"] = motivo
