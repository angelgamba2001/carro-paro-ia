"""
SMARTDATA 360 · Carro de Paro — aplicación web.

    streamlit run app/main.py

Rendimiento: las vistas se importan solo cuando se abren. Cargar todas por
adelantado obliga a esperar scikit-learn, Plotly y PySpark antes de mostrar la
portada, que es justamente donde nadie los necesita.
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

# initial_sidebar_state="auto": en escritorio la barra lateral nace abierta, y en
# un celular nace cerrada. Con "expanded" se abría encima del contenido y había
# que cerrarla a mano en cada recarga del script.
st.set_page_config(page_title="Carro de Paro | SMARTDATA 360", page_icon="🚑", layout="wide",
                   initial_sidebar_state="auto")

from app import sesion  # noqa: E402
from app.componentes import estilos, mensaje_pendiente  # noqa: E402
from src.seguridad.mfa import estado_mfa  # noqa: E402
from src.seguridad.permisos import ROLES, tiene_permiso, vista_permitida  # noqa: E402

estilos()

# (etiqueta, permiso requerido, módulo de la vista)
MENU = [
    ("Tablero", "dashboard.operativo", "tablero"),
    ("Inventario", "inventario.ver", "inventario"),
    ("Lectura OCR", "ocr.usar", "ocr"),
    ("Alertas", "alertas.ver", "alertas"),
    ("Agente IA", "agente.usar", "agente"),
    ("Big Data", "bigdata.ejecutar", "bigdata"),
    ("Catálogo", "catalogo.gestionar", "catalogo"),
    ("Usuarios", "usuarios.gestionar", "usuarios"),
    ("Usuarios", "usuarios.desbloquear", "usuarios"),
    ("Auditoría y seguridad", "auditoria.ver", "auditoria"),
    ("Auditoría y seguridad", "seguridad.ver", "auditoria"),
    ("Mi cuenta", None, "perfil"),
]


def vista(nombre: str):
    """Importa la vista en el momento de usarla; Python la deja en caché después."""
    return importlib.import_module(f"app.vistas.{nombre}")


usuario = sesion.usuario_en_sesion()
if not usuario:
    vista("landing").mostrar()   # portada pública: el sistema, el acceso y los documentos legales
    st.stop()

# Cambio obligatorio de contraseña (usuarios nuevos o restablecidos)
if usuario.get("debe_cambiar_password"):
    vista("perfil").mostrar(usuario, obligatorio=True)
    st.stop()

# Los roles con permisos críticos deben activar el segundo factor antes de operar
if estado_mfa(usuario["id"])["pendiente"]:
    vista("perfil").mostrar(usuario, exigir_mfa=True)
    st.stop()

# Los códigos de respaldo se muestran una sola vez: no se deja continuar sin verlos
if st.session_state.get("codigos_respaldo"):
    vista("perfil").mostrar(usuario, mostrar_respaldo=True)
    st.stop()

opciones = {}
for etiqueta, permiso, modulo in MENU:
    # vista_permitida solo restringe a los VISITANTE: ven únicamente las vistas de sus módulos
    if (permiso is None or tiene_permiso(usuario, permiso)) and vista_permitida(usuario, modulo) \
            and etiqueta not in opciones:
        opciones[etiqueta] = modulo

with st.sidebar:
    st.markdown(f'<div class="identidad"><b>SMARTDATA 360</b><span>carro de paro</span></div>'
                f'<div class="usuario">{usuario["nombre"]}<span>'
                f'{ROLES.get(usuario["rol"], (usuario["rol"],))[0]}</span></div>',
                unsafe_allow_html=True)
    eleccion = st.radio("Menú", list(opciones), label_visibility="collapsed")
    st.markdown('<div class="pie-lateral"></div>', unsafe_allow_html=True)
    if st.button("Cerrar sesión", width="stretch"):
        sesion.cerrar_sesion(registrar=True)
        st.rerun()
    with st.expander("Documentos"):
        from app import legal
        for clave, etiqueta in legal.DOCUMENTOS.items():
            if st.button(etiqueta, key=f"nav_legal_{clave}", width="stretch"):
                st.session_state["legal_interno"] = clave
                st.rerun()

# Si la burbuja pidió abrir el asistente completo, se cambia de pantalla
if st.session_state.pop("ir_a_agente", False) and "Agente IA" in opciones:
    eleccion = "Agente IA"

mensaje_pendiente()
if st.session_state.get("legal_interno"):
    from app import legal
    if st.button("Volver a la aplicación"):
        st.session_state.pop("legal_interno")
        st.rerun()
    st.markdown(f'<div class="documento">{legal.CUERPOS[st.session_state["legal_interno"]]}</div>',
                unsafe_allow_html=True)
else:
    vista(opciones[eleccion]).mostrar(usuario)

# El asistente queda a mano en todas las pantallas, salvo en la suya propia
if eleccion != "Agente IA" and not st.session_state.get("legal_interno"):
    from app import burbuja
    burbuja.mostrar(usuario)
