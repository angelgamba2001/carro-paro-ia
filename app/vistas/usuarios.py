import streamlit as st

from app.componentes import accion, cabecera
from src.seguridad.contrasenas import LONGITUD_MINIMA
from src.seguridad.permisos import ROLES, tiene_permiso
from src.servicios import usuarios as srv


def mostrar(usuario: dict):
    cabecera("Usuarios", "Cuentas, roles y bloqueos")
    if tiene_permiso(usuario, "usuarios.gestionar"):
        _solicitudes(usuario)
    df = srv.listar_usuarios(usuario)
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"activo": st.column_config.CheckboxColumn("activo"),
                                "debe_cambiar_password": st.column_config.CheckboxColumn("cambio pendiente")})
    otros = {f"{r.nombre} ({r.correo})": int(r.id) for r in df.itertuples() if int(r.id) != usuario["id"]}

    if tiene_permiso(usuario, "usuarios.desbloquear"):
        bloqueados = {k: v for k, v in otros.items()
                      if df.loc[df["id"] == v, "bloqueado_hasta"].notna().any()}
        with st.expander(f"Desbloquear cuentas ({len(bloqueados)})", expanded=bool(bloqueados)):
            if bloqueados:
                sel = st.selectbox("Cuenta", list(bloqueados))
                if st.button("Desbloquear"):
                    accion(srv.desbloquear, usuario, bloqueados[sel], exito="Cuenta desbloqueada.")
                    st.rerun()
            else:
                st.caption("No hay cuentas bloqueadas.")

    if not tiene_permiso(usuario, "usuarios.gestionar"):
        return
    izq, der = st.columns(2)
    with izq:
        st.markdown("#### Crear usuario")
        with st.form("nuevo_usuario"):
            nombre = st.text_input("Nombre completo")
            correo = st.text_input("Correo institucional")
            # Por mínimo privilegio, el rol sugerido NO es administrador
            rol = st.selectbox("Rol", list(ROLES), index=list(ROLES).index("ENFERMERO"),
                               format_func=lambda r: ROLES[r][0])
            pw = st.text_input("Contraseña temporal", type="password",
                               help=f"{LONGITUD_MINIMA}+ caracteres con mayúscula, minúscula, número y símbolo")
            st.caption("El usuario deberá cambiarla en su primer ingreso.")
            if st.form_submit_button("Crear", type="primary"):
                accion(srv.crear_usuario, usuario, nombre, correo, pw, rol, exito=f"Usuario {correo} creado.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
    with der:
        st.markdown("#### Modificar cuenta")
        sel = st.selectbox("Usuario", list(otros))
        uid = otros[sel]
        fila = df[df["id"] == uid].iloc[0]
        # Una cuenta recién registrada tiene el perfil SIN_ASIGNAR, que no está en la
        # matriz de roles operativos: ahí el selector arranca en el primero de la lista.
        claves = list(ROLES)
        actual = claves.index(fila["rol"]) if fila["rol"] in claves else 0
        if fila["rol"] not in claves:
            st.caption("Esta cuenta se registró por su cuenta y todavía no tiene perfil. "
                       "Puede asignárselo aquí o desde *Solicitudes de acceso*.")
        nuevo_rol = st.selectbox("Rol", claves, index=actual,
                                 format_func=lambda r: ROLES[r][0], key="rol_edit")
        c1, c2 = st.columns(2)
        if c1.button("Cambiar rol"):
            accion(srv.cambiar_rol, usuario, uid, nuevo_rol, exito="Rol actualizado.")
            st.rerun()
        etiqueta = "Desactivar" if fila["activo"] else "Activar"
        if c2.button(etiqueta):
            accion(srv.cambiar_estado, usuario, uid, not bool(fila["activo"]), exito=f"Cuenta: {etiqueta.lower()}da.")
            st.rerun()
        with st.form("reset_pw"):
            temporal = st.text_input("Nueva contraseña temporal", type="password")
            if st.form_submit_button("Restablecer contraseña"):
                accion(srv.restablecer_password, usuario, uid, temporal, exito="Contraseña restablecida.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()


def _solicitudes(usuario: dict):
    """Personas que se registraron solas y esperan que se les asigne un perfil.

    Verificar el correo demuestra que el buzón es suyo, nada más. Quién puede tocar
    un carro de paro lo decide la institución, y ese es el paso que ocurre aquí."""
    from src import config
    from src.servicios.registro import aprobar, pendientes, rechazar
    solicitudes = pendientes()
    # Con el registro cerrado y sin nada que revisar, el panel sobra
    if not solicitudes and not config.REGISTRO_ABIERTO:
        return
    titulo = f"Solicitudes de acceso ({len(solicitudes)})"
    with st.expander(titulo, expanded=bool(solicitudes)):
        if not solicitudes:
            st.caption("No hay solicitudes pendientes. Aquí aparecen las personas que se "
                       "registraron por su cuenta y ya confirmaron su correo.")
            return
        for s in solicitudes:
            st.markdown(f'<div class="seccion">{s["nombre"]}</div>', unsafe_allow_html=True)
            st.caption(f'{s["correo"]} · solicitó el {s["fecha_creacion"]:%d/%m/%Y a las %H:%M}')
            izq, centro, der = st.columns([2, 1, 1], vertical_alignment="bottom")
            rol = izq.selectbox("Perfil que se le asigna", list(ROLES),
                                format_func=lambda r: ROLES[r][0], key=f"rol_{s['id']}")
            if centro.button("Autorizar", type="primary", width="stretch", key=f"ok_{s['id']}"):
                r = aprobar(usuario, s["id"], rol)
                st.session_state["mensaje_exito" if r.ok else "mensaje_error"] = r.mensaje
                st.rerun()
            if der.button("Rechazar", width="stretch", key=f"no_{s['id']}"):
                r = rechazar(usuario, s["id"], "No corresponde a personal autorizado")
                st.session_state["mensaje_exito" if r.ok else "mensaje_error"] = r.mensaje
                st.rerun()
