import streamlit as st

from app import sesion
from app.componentes import cabecera
from src.seguridad import mfa as srv_mfa
from src.seguridad.autenticacion import cambiar_password
from src.seguridad.contrasenas import LONGITUD_MINIMA
from src.seguridad.permisos import PERMISOS, ROLES, permisos_de_usuario
from src.servicios.consentimiento import VERSION_POLITICAS, historial

CSS = """
<style>
.bloque-seguridad { border-top: 2px solid var(--tinta); padding-top: 1rem; margin-top: .4rem; }
.bloque-seguridad .encabezado { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
.bloque-seguridad h3 { margin: 0; font-size: 1.15rem; }
.bloque-seguridad .estado { font-size: .74rem; font-weight: 500; letter-spacing: .04em;
                            padding: .12rem .45rem; border-radius: 2px; }
.estado.on  { color: var(--monitor); border: 1px solid var(--monitor); }
.estado.off { color: var(--carro);   border: 1px solid var(--carro); }

/* El código QR se presenta como una credencial: marco, no imagen suelta */
.marco-qr {
  display: inline-block; background: #fff; border: 1px solid var(--linea);
  border-top: 3px solid var(--carro); padding: .9rem .9rem .6rem; border-radius: 0;
}
.marco-qr figcaption {
  font-size: .76rem; color: var(--acero); line-height: 1.45;
  text-align: center; padding-top: .55rem;
}
.pasos { counter-reset: paso; margin: 0; padding: 0; list-style: none; }
.pasos li {
  counter-increment: paso; position: relative; padding-left: 2rem;
  margin-bottom: .6rem; font-size: .95rem; line-height: 1.55; color: var(--tinta-suave);
}
.pasos li::before {
  content: counter(paso); position: absolute; left: 0; top: .05rem;
  font-family: var(--mono); font-variant-numeric: tabular-nums;
  font-size: .78rem; font-weight: 600; color: var(--carro);
  border: 1px solid var(--carro); width: 1.35rem; height: 1.35rem;
  display: flex; align-items: center; justify-content: center;
}
.pasos li b { color: var(--tinta); font-weight: 600; }
.permiso-fila { display: grid; grid-template-columns: 13rem 1fr; gap: 1rem; padding: .32rem 0;
                border-bottom: 1px solid var(--linea); font-size: .9rem; }
.permiso-fila code { font-size: .82rem; color: var(--grafito); }
.permiso-fila span { color: var(--tinta-suave); }
</style>
"""


def mostrar(usuario: dict, obligatorio: bool = False, exigir_mfa: bool = False,
            mostrar_respaldo: bool = False):
    st.markdown(CSS, unsafe_allow_html=True)

    # Los códigos de respaldo solo se ven en el momento de generarlos: hasta que la
    # persona confirme que los guardó, no se sigue adelante.
    if mostrar_respaldo:
        cabecera("Guarde sus códigos de respaldo", usuario["correo"])
        st.caption("Le permitirán entrar si pierde el celular o cambia de aparato. Cada uno funciona "
                   "una sola vez y no volverán a mostrarse.")
        _mostrar_codigos_respaldo()
        return

    # --- Paso forzado 1: contraseña inicial ---
    if obligatorio:
        cabecera("Cambie su contraseña", usuario["correo"])
        st.warning("Por seguridad debe cambiar su contraseña antes de continuar.")
        _formulario_password(usuario)
        _salir()
        return

    # --- Paso forzado 2: segundo factor de los roles críticos ---
    if exigir_mfa:
        cabecera("Active la verificación en dos pasos", usuario["correo"])
        st.warning(f"El rol {ROLES[usuario['rol']][0]} tiene permisos críticos, así que necesita un "
                   "segundo factor para entrar al sistema.")
        _activar_mfa(usuario)
        _salir()
        return

    cabecera("Mi cuenta", usuario["correo"])
    contrasena, correo, dos_pasos, permisos = st.tabs(
        ["Contraseña", "Correo", "Verificación en dos pasos", "Mis permisos"])
    with contrasena:
        _formulario_password(usuario)
    with correo:
        _formulario_correo(usuario)
    with dos_pasos:
        _seccion_mfa(usuario)
    with permisos:
        _permisos(usuario)


def _salir():
    if st.button("Cerrar sesión"):
        sesion.cerrar_sesion(registrar=True)
        st.rerun()


# ---------------------------------------------------------------------------
def _formulario_password(usuario: dict):
    with st.form("cambio_pw"):
        actual = st.text_input("Contraseña actual", type="password")
        nueva = st.text_input("Nueva contraseña", type="password",
                              help=f"Mínimo {LONGITUD_MINIMA} caracteres con mayúscula, minúscula, "
                                   "número y símbolo.")
        repetir = st.text_input("Repita la nueva contraseña", type="password")
        ok = st.form_submit_button("Cambiar contraseña", type="primary")
    if ok:
        if nueva != repetir:
            st.error("Las contraseñas no coinciden.")
            return
        errores = cambiar_password(usuario["id"], actual, nueva, st.session_state.get("token_sesion", ""))
        if errores:
            for e in errores:
                st.error(e)
        else:
            st.session_state["usuario"]["debe_cambiar_password"] = 0
            st.session_state["mensaje_exito"] = "Contraseña actualizada."
            st.rerun()


# ---------------------------------------------------------------------------
def _formulario_correo(usuario: dict):
    """Cambio de correo en dos pasos: contraseña actual y código enviado al correo nuevo."""
    from src.servicios import cuenta
    from src.servicios.errores import ErrorNegocio
    st.caption(f"Correo actual: **{usuario['correo']}**. El correo es su usuario para entrar; "
               "para cambiarlo confirmamos que usted controla el buzón nuevo.")
    pendiente = st.session_state.get("cambio_correo_nuevo")
    if not pendiente:
        with st.form("cambio_correo"):
            nuevo = st.text_input("Correo nuevo", max_chars=150)
            password = st.text_input("Contraseña actual", type="password")
            if st.form_submit_button("Enviar código al correo nuevo", type="primary"):
                try:
                    aviso = cuenta.solicitar_cambio_correo(usuario["id"], password, nuevo)
                    st.session_state["cambio_correo_nuevo"] = nuevo.strip().lower()
                    st.session_state["cambio_correo_aviso"] = aviso
                    st.rerun()
                except ErrorNegocio as e:
                    st.error(str(e))
        return
    st.info(st.session_state.get("cambio_correo_aviso", f"Enviamos un código a {pendiente}."))
    with st.form("confirmar_correo"):
        codigo = st.text_input("Código de 6 dígitos", max_chars=6)
        confirmar = st.form_submit_button("Confirmar cambio", type="primary")
    if confirmar:
        try:
            nuevo = cuenta.confirmar_cambio_correo(usuario["id"], codigo)
            st.session_state["usuario"]["correo"] = nuevo
            for k in ("cambio_correo_nuevo", "cambio_correo_aviso"):
                st.session_state.pop(k, None)
            st.session_state["mensaje_exito"] = f"Correo actualizado a {nuevo}. Úselo desde ahora para entrar."
            st.rerun()
        except ErrorNegocio as e:
            st.error(str(e))
    if st.button("Cancelar el cambio"):
        for k in ("cambio_correo_nuevo", "cambio_correo_aviso"):
            st.session_state.pop(k, None)
        st.rerun()


# ---------------------------------------------------------------------------
def _seccion_mfa(usuario: dict):
    estado = srv_mfa.estado_mfa(usuario["id"])
    clase, etiqueta = ("on", "activa") if estado["activo"] else ("off", "sin activar")
    st.markdown(f'<div class="bloque-seguridad"><div class="encabezado">'
                f'<h3>Código temporal del celular</h3>'
                f'<span class="estado {clase}">{etiqueta}</span></div></div>', unsafe_allow_html=True)

    if estado["activo"]:
        _mfa_activa(usuario, estado)
    else:
        st.caption("Añade un código de seis dígitos al iniciar sesión. Funciona con Microsoft "
                   "Authenticator, Google Authenticator o cualquier aplicación compatible, y no "
                   "necesita conexión a internet.")
        _activar_mfa(usuario)

    _seccion_mfa_correo(usuario)


def _seccion_mfa_correo(usuario: dict):
    """Canal alternativo: el código llega al correo institucional.

    Es más cómodo y más débil que el TOTP —quien controle el buzón controla el
    factor—, así que a los roles críticos se les exige igualmente la aplicación."""
    from src.seguridad import mfa_correo
    activo = mfa_correo.disponible(usuario["id"])
    clase, etiqueta = ("on", "activo") if activo else ("off", "sin activar")
    st.markdown(f'<div class="bloque-seguridad"><div class="encabezado">'
                f'<h3>Código al correo institucional</h3>'
                f'<span class="estado {clase}">{etiqueta}</span></div></div>', unsafe_allow_html=True)
    st.caption(f"Recibe el código en {usuario['correo']} en lugar de sacarlo de una aplicación. "
               "Es más cómodo, pero menos seguro: quien acceda a su buzón puede leer el código. "
               "Úselo si no puede instalar la aplicación de autenticación.")

    estado = srv_mfa.estado_mfa(usuario["id"])
    if estado["obligatorio"] and not estado["activo"] and not activo:
        st.info("Su rol tiene permisos críticos. Puede usar el correo, pero de todos modos "
                "tendrá que activar la aplicación de autenticación para operar.")

    izq, der = st.columns(2, gap="large")
    if activo:
        if izq.button("Desactivar el envío al correo", width="stretch"):
            if not estado["activo"]:
                st.error("Es su único segundo factor. Active primero la aplicación de "
                         "autenticación, o quedaría sin ninguna verificación.")
            else:
                mfa_correo.activar(usuario["id"], False)
                st.session_state["mensaje_exito"] = "Ya no recibirá códigos por correo."
                st.rerun()
        if der.button("Enviarme un código de prueba", width="stretch"):
            ok, aviso = mfa_correo.enviar_codigo(usuario["id"])
            (st.success if ok else st.warning)(aviso)
    else:
        if izq.button("Activar el envío al correo", type="primary", width="stretch"):
            mfa_correo.activar(usuario["id"], True)
            st.session_state["mensaje_exito"] = (
                f"Listo. A partir de ahora puede recibir el código en {usuario['correo']}.")
            st.rerun()


def _activar_mfa(usuario: dict):
    if "mfa_uri" not in st.session_state:
        if st.button("Generar código QR", type="primary"):
            secreto, uri = srv_mfa.iniciar_activacion(usuario["id"], usuario["correo"])
            st.session_state["mfa_uri"] = uri
            st.session_state["mfa_secreto"] = secreto
            st.rerun()
        _mostrar_codigos_respaldo()
        return

    izq, der = st.columns([0.85, 1.15], gap="large")
    with izq:
        # El QR se incrusta en el propio HTML para que quede dentro del marco:
        # st.image viviría en otro contenedor y el marco aparecería vacío.
        import base64
        png = base64.b64encode(srv_mfa.qr_png(st.session_state["mfa_uri"])).decode()
        st.markdown(f'<figure class="marco-qr">'
                    f'<img src="data:image/png;base64,{png}" width="200" height="200" '
                    f'alt="Código QR para configurar la verificación en dos pasos">'
                    f'<figcaption>{usuario["correo"]}</figcaption></figure>', unsafe_allow_html=True)
    with der:
        st.markdown("""
        <ol class="pasos">
          <li>Abra su aplicación de autenticación en el celular.</li>
          <li>Elija <b>Agregar cuenta</b> y luego <b>Cuenta personal</b> u <b>Otra</b>.</li>
          <li>Apunte la cámara al código de la izquierda.</li>
          <li>Escriba aquí el código de seis dígitos que aparece.</li>
        </ol>
        """, unsafe_allow_html=True)
        with st.expander("La cámara no lee el código"):
            st.caption("Escriba esta clave manualmente en la aplicación:")
            st.code(st.session_state["mfa_secreto"])
        with st.form("confirmar_mfa"):
            codigo = st.text_input("Código de 6 dígitos", max_chars=6, placeholder="000000")
            activar = st.form_submit_button("Activar", type="primary")
        if activar:
            try:
                st.session_state["codigos_respaldo"] = srv_mfa.confirmar_activacion(usuario["id"], codigo)
                st.session_state.pop("mfa_uri", None)
                st.session_state.pop("mfa_secreto", None)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    _mostrar_codigos_respaldo()


def _mfa_activa(usuario: dict, estado: dict):
    restantes = srv_mfa.codigos_respaldo_restantes(usuario["id"])
    st.caption(f"Quedan {restantes} códigos de respaldo sin usar. Sirven para entrar si pierde el "
               "celular, y cada uno funciona una sola vez.")
    if restantes <= 2:
        st.warning("Le quedan pocos códigos de respaldo. Conviene generar nuevos y guardarlos aparte.")

    col1, col2 = st.columns(2, gap="large")
    with col1.form("regenerar_respaldo"):
        st.caption("Generar códigos de respaldo nuevos")
        codigo = st.text_input("Código actual", max_chars=9, key="pw_regen")
        if st.form_submit_button("Generar nuevos códigos"):
            try:
                st.session_state["codigos_respaldo"] = srv_mfa.regenerar_codigos_respaldo(
                    usuario["id"], codigo)
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    with col2:
        if estado["obligatorio"]:
            st.caption("Su rol tiene permisos críticos, así que la verificación no puede desactivarse.")
        else:
            with st.form("desactivar_mfa"):
                st.caption("Desactivar la verificación en dos pasos")
                codigo = st.text_input("Código actual", max_chars=9, key="pw_off")
                if st.form_submit_button("Desactivar"):
                    try:
                        srv_mfa.desactivar(usuario["id"], codigo)
                        st.session_state["mensaje_exito"] = "Verificación en dos pasos desactivada."
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
    _mostrar_codigos_respaldo()


def _mostrar_codigos_respaldo():
    """Los códigos se ven una sola vez: en la base de datos quedan con hash."""
    codigos = st.session_state.get("codigos_respaldo")
    if not codigos:
        return
    st.success("Guarde estos códigos en un lugar seguro, distinto de su celular. No volverán a mostrarse.")
    st.code("\n".join(codigos))
    c1, c2 = st.columns([1, 3])
    c1.download_button("Descargar", "\n".join(codigos), "codigos_respaldo_carro_paro.txt", "text/plain")
    if c2.button("Ya los guardé"):
        st.session_state.pop("codigos_respaldo")
        st.rerun()


# ---------------------------------------------------------------------------
def _permisos(usuario: dict):
    nombre, descripcion = ROLES.get(usuario["rol"], (usuario["rol"], ""))
    st.markdown(f"**{nombre}.** {descripcion}")
    extras = [ROLES[r][0] for r in usuario.get("roles_extra") or [] if r in ROLES]
    if extras:
        st.caption("Roles adicionales: " + ", ".join(extras))
    filas = "".join(f'<div class="permiso-fila"><code>{p}</code><span>{PERMISOS[p]}</span></div>'
                    for p in sorted(permisos_de_usuario(usuario)))
    st.markdown(filas, unsafe_allow_html=True)

    st.markdown('<div class="bloque-seguridad"><h3>Aceptación de políticas</h3></div>',
                unsafe_allow_html=True)
    registros = historial(usuario["id"])
    if registros:
        for r in registros:
            marca = "" if not r["revocado"] else " (revocada)"
            st.caption(f"Versión {r['version']} aceptada el "
                       f"{r['fecha']:%d/%m/%Y a las %H:%M} desde {r['origen'].lower()}{marca}")
    else:
        st.caption(f"No hay una aceptación registrada de la versión {VERSION_POLITICAS}.")
