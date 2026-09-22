"""
SMARTDATA 360 · Carro de Paro — aplicación web (Streamlit).

    streamlit run app/main.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="Carro de Paro · SMARTDATA 360", page_icon="🚑", layout="wide")

from app import sesion  # noqa: E402
from app.componentes import estilos, mensaje_pendiente  # noqa: E402
from app.vistas import (agente, alertas, auditoria, bigdata, catalogo, inventario, ocr,  # noqa: E402
                        perfil, tablero, usuarios)
from src.database.connection import base_disponible  # noqa: E402
from src.seguridad.autenticacion import autenticar  # noqa: E402
from src.seguridad.permisos import ROLES, tiene_permiso  # noqa: E402
from src.servicios.inventario import recalcular_estados  # noqa: E402

estilos()

# (etiqueta, permiso requerido, función de la vista)
MENU = [
    ("Tablero", "dashboard.operativo", tablero.mostrar),
    ("Inventario", "inventario.ver", inventario.mostrar),
    ("Lectura OCR", "ocr.usar", ocr.mostrar),
    ("Alertas", "alertas.ver", alertas.mostrar),
    ("Agente IA", "agente.usar", agente.mostrar),
    ("Big Data", "bigdata.ejecutar", bigdata.mostrar),
    ("Catálogo", "catalogo.gestionar", catalogo.mostrar),
    ("Usuarios", "usuarios.gestionar", usuarios.mostrar),
    ("Usuarios", "usuarios.desbloquear", usuarios.mostrar),
    ("Auditoría y seguridad", "auditoria.ver", auditoria.mostrar),
    ("Auditoría y seguridad", "seguridad.ver", auditoria.mostrar),
    ("Mi cuenta", None, perfil.mostrar),
]


def pantalla_login():
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.markdown("## 🚑 Carro de Paro")
        st.caption("SMARTDATA 360 · Control inteligente de medicamentos de reanimación")
        if "motivo_salida" in st.session_state:
            st.info(st.session_state.pop("motivo_salida"))
        if not base_disponible():
            st.error("No hay conexión con la base de datos. Revise el archivo .env y que MySQL esté activo.")
            st.stop()
        with st.form("login"):
            correo = st.text_input("Correo institucional", placeholder="usuario@hospital.com")
            password = st.text_input("Contraseña", type="password")
            entrar = st.form_submit_button("Ingresar", type="primary", width="stretch")
        if entrar:
            r = autenticar(correo, password)
            if r.ok:
                sesion.iniciar_sesion(r.usuario)
                recalcular_estados()   # mantiene estados y alertas al día con la fecha actual
                st.rerun()
            else:
                st.error(r.mensaje)
                if r.intentos_restantes is not None and r.intentos_restantes <= 2:
                    st.warning(f"Intentos restantes antes del bloqueo temporal: {r.intentos_restantes}")


usuario = sesion.usuario_en_sesion()
if not usuario:
    pantalla_login()
    st.stop()

# Cambio obligatorio de contraseña (usuarios nuevos o restablecidos)
if usuario.get("debe_cambiar_password"):
    perfil.mostrar(usuario, obligatorio=True)
    st.stop()

opciones = {}
for etiqueta, permiso, vista in MENU:
    if (permiso is None or tiene_permiso(usuario, permiso)) and etiqueta not in opciones:
        opciones[etiqueta] = vista

with st.sidebar:
    st.markdown(f"**{usuario['nombre']}**")
    st.caption(ROLES.get(usuario["rol"], (usuario["rol"],))[0])
    eleccion = st.radio("Menú", list(opciones), label_visibility="collapsed")
    st.divider()
    if st.button("Cerrar sesión", width="stretch"):
        sesion.cerrar_sesion(registrar=True)
        st.rerun()

mensaje_pendiente()
opciones[eleccion](usuario)
