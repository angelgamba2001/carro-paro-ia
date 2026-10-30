import streamlit as st

from app.componentes import accion, cabecera
from src.seguridad.contrasenas import LONGITUD_MINIMA
from src.seguridad.permisos import MODULOS_VISITANTE, PERMISOS, ROLES, modulos_de, tiene_permiso
from src.servicios import roles as srv_roles
from src.servicios import usuarios as srv


def _roles_personalizados(usuario: dict):
    """Crear roles con los permisos que se elijan, cambiarlos o eliminarlos."""
    try:
        roles = srv_roles.listar_roles_personalizados(usuario)
    except Exception:                                  # noqa: BLE001  (falta aplicar la migración)
        st.warning("Falta aplicar la migración de seguridad: python scripts/migrar_seguridad.py")
        return
    # Sección fija (no un expander): un expander de Streamlit se cierra en cada cambio de
    # los selectores de adentro y obligaba a reabrirlo para terminar de editar un rol.
    st.markdown(f"#### Roles personalizados ({len(roles)})")
    with st.container(border=True):
        if roles:
            st.dataframe([{"rol": r["nombre"], "permisos": ", ".join(r["permisos"]),
                           "personas": r["usuarios"]} for r in roles], hide_index=True, width="stretch")
        else:
            st.caption("Aún no hay roles personalizados. Los roles base (Administrador, Enfermero…) no se modifican.")
        with st.form("nuevo_rol", clear_on_submit=True):
            st.markdown("**Crear un rol**")
            nombre = st.text_input("Nombre del rol", max_chars=60)
            descripcion = st.text_input("Descripción", max_chars=200)
            permisos = st.multiselect("Permisos", list(PERMISOS), format_func=lambda p: f"{p} — {PERMISOS[p]}")
            if st.form_submit_button("Crear rol", type="primary"):
                accion(srv_roles.crear_rol, usuario, nombre, descripcion, permisos, exito="Rol creado.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
        if roles:
            st.markdown("**Modificar o eliminar un rol**")
            codigo = st.selectbox("Rol", [r["codigo"] for r in roles],
                                  format_func=lambda c: next(r["nombre"] for r in roles if r["codigo"] == c))
            actual = next(r for r in roles if r["codigo"] == codigo)
            nuevos = st.multiselect("Permisos del rol", list(PERMISOS), default=actual["permisos"],
                                    format_func=lambda p: f"{p} — {PERMISOS[p]}", key=f"permisos_{codigo}")
            b1, b2 = st.columns(2)
            if b1.button("Guardar permisos", key=f"guardar_{codigo}"):
                accion(srv_roles.cambiar_permisos_rol, usuario, codigo, nuevos, exito="Permisos del rol actualizados.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
            if b2.button("Eliminar rol", key=f"borrar_{codigo}"):
                accion(srv_roles.eliminar_rol, usuario, codigo, exito="Rol eliminado.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()


def _selector_modulos(clave: str, por_defecto=None):
    """Casillas de módulos para una cuenta Visitante. Siempre son de solo lectura."""
    return st.multiselect(
        "Módulos que puede abrir (solo para el rol Visitante)", list(MODULOS_VISITANTE),
        default=list(por_defecto or []), key=clave,
        format_func=lambda m: f"{MODULOS_VISITANTE[m][0]} — {MODULOS_VISITANTE[m][1]}",
        help="El visitante solo consulta: nunca registra, edita, da de baja ni gestiona. "
             "Si elige el tablero, también verá los datos de inventario y alertas que ese tablero muestra.")


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
    _roles_personalizados(usuario)
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
            modulos_nuevo = _selector_modulos("modulos_nuevo")
            st.caption("El usuario deberá cambiarla en su primer ingreso.")
            if st.form_submit_button("Crear", type="primary"):
                accion(srv.crear_usuario, usuario, nombre, correo, pw, rol, modulos_nuevo,
                       exito=f"Usuario {correo} creado.")
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
                                 format_func=lambda r: ROLES[r][0], key=f"rol_edit_{uid}")  # una clave por cuenta:
        # con una clave fija, Streamlit conservaba el rol elegido para la cuenta anterior
        c1, c2 = st.columns(2)
        if c1.button("Cambiar rol"):
            accion(srv.cambiar_rol, usuario, uid, nuevo_rol, exito="Rol actualizado.")
            st.rerun()
        if fila["rol"] == "VISITANTE":
            modulos_cuenta = _selector_modulos(f"modulos_edit_{uid}", modulos_de(fila.to_dict()))
            if st.button("Guardar módulos"):
                accion(srv.cambiar_modulos, usuario, uid, modulos_cuenta, exito="Módulos actualizados.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
        if fila["rol"] != "VISITANTE":
            crudo = fila.get("roles_adicionales")
            actuales = [r for r in (crudo.split(",") if isinstance(crudo, str) else []) if r in ROLES]
            elegibles = [r for r in ROLES if r not in ("VISITANTE", fila["rol"])]
            extras = st.multiselect("Roles adicionales (suman permisos al rol principal)", elegibles,
                                    default=[r for r in actuales if r in elegibles], key=f"extras_{uid}",
                                    format_func=lambda r: ROLES[r][0])
            if st.button("Guardar roles adicionales"):
                accion(srv_roles.cambiar_roles_adicionales, usuario, uid, extras, exito="Roles adicionales actualizados.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
            crudo_p = fila.get("permisos_individuales")
            actuales_p = [p for p in (crudo_p.split(",") if isinstance(crudo_p, str) else []) if p in PERMISOS]
            individuales = st.multiselect(
                "Permisos individuales (se suman a los de sus roles)", list(PERMISOS), default=actuales_p,
                key=f"permisos_ind_{uid}", format_func=lambda p: f"{p} — {PERMISOS[p]}",
                help="Permiten que dos personas con el mismo rol tengan permisos distintos.")
            if st.button("Guardar permisos individuales"):
                accion(srv_roles.cambiar_permisos_individuales, usuario, uid, individuales,
                       exito="Permisos individuales actualizados.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
        etiqueta = "Desactivar" if fila["activo"] else "Activar"
        if c2.button(etiqueta):
            accion(srv.cambiar_estado, usuario, uid, not bool(fila["activo"]), exito=f"Cuenta: {etiqueta.lower()}da.")
            st.rerun()
        with st.expander("Eliminar cuenta"):
            st.caption("Solo se pueden eliminar cuentas sin historial (por ejemplo, creadas por error). "
                       "Si ya registró movimientos o alertas, desactívela. Esta acción no se puede deshacer.")
            with st.form(f"eliminar_{uid}"):
                escrito = st.text_input("Escriba el correo de la cuenta para confirmar",
                                        placeholder=str(fila["correo"]))
                if st.form_submit_button("Eliminar cuenta definitivamente"):
                    accion(srv.eliminar_usuario, usuario, uid, escrito,
                           exito=f"Cuenta {fila['correo']} eliminada.")
                    if "mensaje_exito" in st.session_state:
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
