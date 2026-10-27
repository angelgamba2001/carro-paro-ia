"""Pantalla de restablecimiento de contraseña, autorizada con el segundo factor."""
import streamlit as st

from src.seguridad.contrasenas import LONGITUD_MINIMA
from src.seguridad.recuperacion import puede_restablecer, restablecer


def mostrar():
    _, centro, _ = st.columns([1, 1.25, 1])
    with centro:
        st.markdown('<div class="acceso-marco">', unsafe_allow_html=True)
        if st.session_state.get("recuperar_id"):
            _paso_codigo()
        else:
            _paso_correo()
        st.markdown("</div>", unsafe_allow_html=True)


def _paso_correo():
    st.markdown('<h1>Restablecer contraseña</h1>'
                '<p class="sub">Necesitará su aplicación de autenticación o uno de sus códigos de '
                'respaldo; si no tiene verificación en dos pasos, le enviaremos un código a su correo.</p>'
                '<div class="regla-acceso"></div>', unsafe_allow_html=True)
    with st.form("recuperar_correo", border=False):
        correo = st.text_input("Correo institucional", placeholder="usuario@hospital.com")
        seguir = st.form_submit_button("Continuar", type="primary", width="stretch")
    if seguir:
        r = puede_restablecer(correo)
        if r.ok:
            st.session_state["recuperar_id"] = r.usuario_id
            st.session_state["recuperar_cuenta"] = correo.strip().lower()
            st.session_state["recuperar_canal"] = r.canal
            if r.canal in ("correo", "correo_temporal"):    # sin app de autenticación, el código va al buzón
                from src.seguridad.mfa_correo import enviar_codigo
                enviar_codigo(r.usuario_id)
            st.rerun()
        else:
            st.info(r.mensaje)
            st.caption("Si no recibe el código o su cuenta está bloqueada, solicite el restablecimiento "
                       "al área de soporte de sistemas.")
    if st.button("Volver al acceso", width="stretch"):
        st.session_state["pantalla"] = "acceso"
        st.rerun()


def _paso_codigo():
    st.markdown(f'<h1>Nueva contraseña</h1><p class="sub">Cuenta: '
                f'{st.session_state["recuperar_cuenta"]}</p><div class="regla-acceso"></div>',
                unsafe_allow_html=True)
    canal = st.session_state.get("recuperar_canal", "app")
    ayuda = {"app": "Los seis dígitos de su aplicación, o un código de respaldo.",
             "correo": "El código de seis dígitos que acabamos de enviar a su correo.",
             "correo_temporal": "El código de seis dígitos que acabamos de enviar a su correo.",
             "ambos": "De su aplicación, un código de respaldo, o el que pida por correo."}
    if canal in ("correo", "correo_temporal"):
        st.info("Le enviamos un código a su correo institucional. Vence en unos minutos.")
    with st.form("recuperar_codigo", border=False):
        codigo = st.text_input("Código de verificación", max_chars=9,
                               help=ayuda.get(canal, ayuda["app"]))
        nueva = st.text_input("Nueva contraseña", type="password",
                              help=f"Mínimo {LONGITUD_MINIMA} caracteres con mayúscula, minúscula, "
                                   "número y símbolo.")
        repetir = st.text_input("Repita la nueva contraseña", type="password")
        aplicar = st.form_submit_button("Restablecer contraseña", type="primary", width="stretch")
    if aplicar:
        r = restablecer(st.session_state["recuperar_id"], codigo, nueva, repetir)
        if r.ok:
            for clave in ("recuperar_id", "recuperar_cuenta", "recuperar_canal"):
                st.session_state.pop(clave, None)
            st.session_state["pantalla"] = "acceso"
            st.session_state["mensaje_acceso"] = r.mensaje
            st.rerun()
        st.error(r.mensaje)
        for e in r.errores or []:
            st.caption(f"· {e}")
    if canal in ("correo", "ambos", "correo_temporal"):
        if st.button("Enviarme un código al correo", width="stretch"):
            from src.seguridad.mfa_correo import enviar_codigo
            ok, aviso = enviar_codigo(st.session_state["recuperar_id"])
            (st.success if ok else st.warning)(aviso)

    if st.button("Cancelar", width="stretch"):
        for clave in ("recuperar_id", "recuperar_cuenta", "recuperar_canal"):
            st.session_state.pop(clave, None)
        st.session_state["pantalla"] = "acceso"
        st.rerun()
