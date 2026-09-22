import streamlit as st

from app.componentes import accion, cabecera
from src.seguridad.contrasenas import LONGITUD_MINIMA
from src.seguridad.permisos import ROLES, tiene_permiso
from src.servicios import usuarios as srv


def mostrar(usuario: dict):
    cabecera("Usuarios", "Cuentas, roles y bloqueos")
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
        nuevo_rol = st.selectbox("Rol", list(ROLES), index=list(ROLES).index(fila["rol"]),
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
