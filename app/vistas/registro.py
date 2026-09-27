"""Pantalla de registro por cuenta propia: datos, verificación del correo y espera."""
import streamlit as st

from src import config
from src.seguridad.contrasenas import LONGITUD_MINIMA
from src.servicios.registro import reenviar_codigo, solicitar_cuenta, verificar_correo
from src.servicios.consentimiento import TEXTO_ACEPTACION, registrar_aceptacion


def mostrar():
    _, centro, _ = st.columns([1, 1.25, 1])
    with centro:
        st.markdown('<div class="acceso-marco">', unsafe_allow_html=True)
        if st.session_state.get("registro_listo"):
            _paso_final()
        elif st.session_state.get("registro_id"):
            _paso_codigo()
        else:
            _paso_datos()
        st.markdown("</div>", unsafe_allow_html=True)


def _volver_al_acceso(etiqueta="Volver al acceso"):
    if st.button(etiqueta, width="stretch"):
        for clave in ("registro_id", "registro_listo", "registro_correo"):
            st.session_state.pop(clave, None)
        st.session_state["pantalla"] = "acceso"
        st.rerun()


# ---------------------------------------------------------------------------
def _paso_datos():
    st.markdown('<h1>Crear cuenta</h1>'
                '<p class="sub">Use su correo habitual: allí recibirá el código de confirmación '
                'y los avisos de seguridad.</p><div class="regla-acceso"></div>',
                unsafe_allow_html=True)

    if not config.REGISTRO_ABIERTO:
        st.info("El registro por cuenta propia está deshabilitado en esta instalación. "
                "Solicite su acceso al área de sistemas.")
        _volver_al_acceso()
        return

    with st.form("registro_datos", border=False):
        nombre = st.text_input("Nombre completo", placeholder="Alvaro Guevara")
        correo = st.text_input("Correo electrónico", placeholder="nombre@gmail.com")
        password = st.text_input("Contraseña", type="password",
                                 help=f"Mínimo {LONGITUD_MINIMA} caracteres con mayúscula, "
                                      "minúscula, número y símbolo.")
        repetir = st.text_input("Repita la contraseña", type="password")
        acepta = st.checkbox(TEXTO_ACEPTACION)
        enviar = st.form_submit_button("Crear cuenta", type="primary", width="stretch")

    if enviar:
        if not acepta:
            st.warning("Debe aceptar los términos y el aviso de tratamiento de datos.")
        else:
            r = solicitar_cuenta(nombre, correo, password, repetir)
            if r.ok:
                st.session_state["registro_id"] = r.usuario_id
                st.session_state["registro_correo"] = correo.strip().lower()
                st.session_state["registro_acepto"] = True
                st.rerun()
            st.error(r.mensaje)
            for e in r.errores or []:
                st.caption(f"· {e}")

    st.markdown('<p class="nota-acceso">Crear la cuenta confirma que el correo es suyo. '
                'El perfil de trabajo lo asigna la institución: hasta entonces la cuenta '
                'existe pero no da acceso a los carros de paro.</p>', unsafe_allow_html=True)
    _volver_al_acceso("Ya tengo cuenta")


def _paso_codigo():
    correo = st.session_state.get("registro_correo", "su correo")
    st.markdown(f'<h1>Confirme su correo</h1><p class="sub">Enviamos un código de seis dígitos '
                f'a {correo}.</p><div class="regla-acceso"></div>', unsafe_allow_html=True)
    st.caption("Si no aparece en unos minutos, revise la carpeta de correo no deseado.")

    with st.form("registro_codigo", border=False):
        codigo = st.text_input("Código de verificación", max_chars=6)
        confirmar = st.form_submit_button("Confirmar", type="primary", width="stretch")

    if confirmar:
        r = verificar_correo(st.session_state["registro_id"], codigo)
        if r.ok:
            if st.session_state.pop("registro_acepto", False):
                registrar_aceptacion(st.session_state["registro_id"], origen="WEB")
            st.session_state["registro_listo"] = r.mensaje
            st.rerun()
        st.error(r.mensaje)

    if st.button("Enviarme otro código", width="stretch"):
        r = reenviar_codigo(st.session_state["registro_id"])
        (st.success if r.ok else st.warning)(r.mensaje)
    _volver_al_acceso("Cancelar")


def _paso_final():
    st.markdown('<h1>Listo</h1><div class="regla-acceso"></div>', unsafe_allow_html=True)
    st.success(st.session_state["registro_listo"])
    if "Un administrador" in st.session_state["registro_listo"]:
        st.caption("Mientras tanto no hace falta que esté pendiente: le llegará un correo "
                   "en cuanto su acceso quede autorizado.")
    _volver_al_acceso("Ir al acceso")
