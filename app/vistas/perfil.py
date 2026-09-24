import streamlit as st

from app import sesion
from app.componentes import cabecera
from src.seguridad.autenticacion import cambiar_password
from src.seguridad.contrasenas import LONGITUD_MINIMA
from src.seguridad import mfa as srv_mfa
from src.seguridad.permisos import PERMISOS, ROLES, permisos_de


def mostrar(usuario: dict, obligatorio: bool = False, exigir_mfa: bool = False):
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

    _verificacion_dos_pasos(usuario, exigir_mfa)
    if exigir_mfa:
        if st.button("Cerrar sesión"):
            sesion.cerrar_sesion(registrar=True)
            st.rerun()
        return
    st.subheader("Mis permisos")
    st.caption(f"Rol: {ROLES[usuario['rol']][0]} — {ROLES[usuario['rol']][1]}")
    for p in sorted(permisos_de(usuario["rol"])):
        st.markdown(f"- `{p}` · {PERMISOS[p]}")


def _verificacion_dos_pasos(usuario: dict, exigir: bool = False):
    st.divider()
    st.subheader("Verificación en dos pasos")
    estado = srv_mfa.estado_mfa(usuario["id"])

    if estado["activo"]:
        restantes = srv_mfa.codigos_respaldo_restantes(usuario["id"])
        st.success(f"Activa. Le quedan {restantes} códigos de respaldo sin usar.")
        if restantes <= 2:
            st.warning("Le quedan pocos códigos de respaldo: conviene generar nuevos.")
        col1, col2 = st.columns(2)
        with col1.form("regenerar_respaldo"):
            codigo = st.text_input("Código actual para generar nuevos códigos de respaldo", max_chars=9)
            if st.form_submit_button("Generar nuevos códigos"):
                try:
                    st.session_state["codigos_respaldo"] = srv_mfa.regenerar_codigos_respaldo(
                        usuario["id"], codigo)
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
        if not estado["obligatorio"]:
            with col2.form("desactivar_mfa"):
                codigo = st.text_input("Código actual para desactivar", max_chars=9, key="pw_off")
                if st.form_submit_button("Desactivar verificación en dos pasos"):
                    try:
                        srv_mfa.desactivar(usuario["id"], codigo)
                        st.session_state["mensaje_exito"] = "Verificación en dos pasos desactivada."
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        else:
            col2.caption("Su rol tiene permisos críticos, por lo que no puede desactivarla.")
        _mostrar_codigos_respaldo()
        return

    if exigir:
        st.warning("Su rol tiene permisos críticos: debe activar la verificación en dos pasos para continuar.")
    else:
        st.caption("Agrega un código de 6 dígitos de su celular al ingresar. Funciona con Microsoft "
                   "Authenticator, Google Authenticator o cualquier app compatible, y no requiere internet.")

    if st.button("Generar código QR", type="primary"):
        secreto, uri = srv_mfa.iniciar_activacion(usuario["id"], usuario["correo"])
        st.session_state["mfa_uri"] = uri
        st.session_state["mfa_secreto"] = secreto

    if "mfa_uri" in st.session_state:
        col1, col2 = st.columns([1, 1.4])
        col1.image(srv_mfa.qr_png(st.session_state["mfa_uri"]), width=220)
        with col2:
            st.markdown("1. Abra su aplicación de autenticación.\n"
                        "2. Elija **Agregar cuenta** → **Cuenta personal / Otra**.\n"
                        "3. Escanee el código QR.\n"
                        "4. Escriba abajo el código de 6 dígitos que aparece.")
            with st.expander("¿No puede escanear? Escriba la clave manualmente"):
                st.code(st.session_state["mfa_secreto"])
            with st.form("confirmar_mfa"):
                codigo = st.text_input("Código de 6 dígitos", max_chars=6)
                if st.form_submit_button("Activar", type="primary"):
                    try:
                        st.session_state["codigos_respaldo"] = srv_mfa.confirmar_activacion(
                            usuario["id"], codigo)
                        st.session_state.pop("mfa_uri", None)
                        st.session_state.pop("mfa_secreto", None)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
    _mostrar_codigos_respaldo()


def _mostrar_codigos_respaldo():
    """Los códigos solo se muestran una vez: después quedan guardados con hash."""
    codigos = st.session_state.get("codigos_respaldo")
    if not codigos:
        return
    st.success("Guarde estos códigos de respaldo en un lugar seguro. No volverán a mostrarse.")
    st.code("\n".join(codigos))
    st.download_button("Descargar códigos", "\n".join(codigos), "codigos_respaldo_carro_paro.txt",
                       "text/plain")
    if st.button("Ya los guardé"):
        st.session_state.pop("codigos_respaldo")
        st.rerun()
