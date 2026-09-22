import streamlit as st

from app import sesion
from app.componentes import cabecera
from src.seguridad.autenticacion import cambiar_password
from src.seguridad.contrasenas import LONGITUD_MINIMA
from src.seguridad.permisos import PERMISOS, ROLES, permisos_de


def mostrar(usuario: dict, obligatorio: bool = False):
    cabecera("Mi cuenta", usuario["correo"])
    if obligatorio:
        st.warning("Por seguridad debe cambiar su contraseña antes de continuar.")
    with st.form("cambio_pw"):
        actual = st.text_input("Contraseña actual", type="password")
        nueva = st.text_input("Nueva contraseña", type="password",
                              help=f"Mínimo {LONGITUD_MINIMA} caracteres con mayúscula, minúscula, número y símbolo.")
        repetir = st.text_input("Repita la nueva contraseña", type="password")
        ok = st.form_submit_button("Cambiar contraseña", type="primary")
    if ok:
        if nueva != repetir:
            st.error("Las contraseñas no coinciden.")
        else:
            errores = cambiar_password(usuario["id"], actual, nueva)
            if errores:
                for e in errores:
                    st.error(e)
            else:
                st.session_state["usuario"]["debe_cambiar_password"] = 0
                st.session_state["mensaje_exito"] = "Contraseña actualizada."
                st.rerun()
    if obligatorio:
        if st.button("Cerrar sesión"):
            sesion.cerrar_sesion(registrar=True)
            st.rerun()
        return
    st.subheader("Mis permisos")
    st.caption(f"Rol: {ROLES[usuario['rol']][0]} — {ROLES[usuario['rol']][1]}")
    for p in sorted(permisos_de(usuario["rol"])):
        st.markdown(f"- `{p}` · {PERMISOS[p]}")
