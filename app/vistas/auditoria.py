import plotly.express as px
import streamlit as st

from app.componentes import accion, cabecera, descargas
from src import config
from src.seguridad import ajustes
from src.seguridad.permisos import tiene_permiso
from src.servicios import usuarios as srv


def mostrar(usuario: dict):
    cabecera("Auditoría y seguridad", "Trazabilidad de acciones y eventos de acceso")
    dias = st.select_slider("Periodo (días)", [1, 7, 30, 90, 365], value=30)
    pestañas = []
    if tiene_permiso(usuario, "auditoria.ver"):
        pestañas.append("Log de auditoría")
    if tiene_permiso(usuario, "seguridad.ver"):
        pestañas.append("Eventos de seguridad")
        pestañas.append("Errores del sistema")
        if (config.CORREO_MODO or "").lower() == "archivo":
            pestañas.append("Correos simulados")
    if tiene_permiso(usuario, "usuarios.gestionar"):
        pestañas.append("Configuración")
    for nombre, tab in zip(pestañas, st.tabs(pestañas)):
        with tab:
            if nombre == "Log de auditoría":
                _log_auditoria(usuario, dias)
            elif nombre == "Errores del sistema":
                _errores(usuario, dias)
            elif nombre == "Correos simulados":
                _correos(usuario)
            elif nombre == "Configuración":
                _configuracion(usuario)
            else:
                _eventos(usuario, dias)


def _log_auditoria(usuario: dict, dias: int):
    df = srv.log_auditoria(usuario, dias)
    if df.empty:
        st.info("Sin registros en el periodo.")
        return
    c1, c2 = st.columns(2)
    acciones = c1.multiselect("Acción", sorted(df["accion"].unique()))
    origenes = c2.multiselect("Origen", sorted(df["origen"].unique()))
    if acciones:
        df = df[df["accion"].isin(acciones)]
    if origenes:
        df = df[df["origen"].isin(origenes)]
    st.dataframe(df, hide_index=True, width="stretch")
    descargas(df, "auditoria", "aud")


def _errores(usuario: dict, dias: int):
    if tiene_permiso(usuario, "usuarios.gestionar"):
        st.caption("Para comprobar el registro de errores sin romper nada, genere un error controlado: "
                   "queda en esta tabla, en data/logs/errores.log y en el log de auditoría.")
        if st.button("Generar error de prueba"):
            accion(srv.generar_error_prueba, usuario, exito="Error de prueba registrado.")
            if "mensaje_exito" in st.session_state:
                st.rerun()
    df = srv.errores_sistema(usuario, dias)
    if df.empty:
        st.info("Sin errores registrados en el periodo.")
        return
    st.caption("Errores de la aplicación y de la API. También quedan en el archivo "
               "data/logs/errores.log, que sigue funcionando aunque la base de datos esté caída.")
    st.dataframe(df.drop(columns=["traza"]), hide_index=True, width="stretch")
    with st.expander("Ver la traza del error más reciente"):
        st.code(str(df.iloc[0]["traza"] or ""), language=None)
    descargas(df, "errores_sistema", "err")


def _correos(usuario: dict):
    st.caption("El envío de correo está en modo demostración (CORREO_MODO=archivo): los mensajes "
               "no salen del servidor. Aquí se ven los que se habrían enviado, con su código, para "
               "completar el restablecimiento de contraseña, el cambio de correo o el registro.")
    if st.button("Actualizar bandeja"):
        st.rerun()
    correos = srv.correos_simulados(usuario)
    if not correos:
        st.info("Todavía no se ha generado ningún correo.")
        return
    st.dataframe(correos, hide_index=True, width="stretch")


def _configuracion(usuario: dict):
    st.caption("Tiempos de expiración. Se aplican sin reiniciar (en unos segundos) y cada cambio "
               "queda en el log de auditoría. El valor de arranque viene del archivo .env.")
    with st.form("ajustes_seguridad"):
        nuevos = {}
        for clave, (etiqueta, minimo, maximo) in ajustes.AJUSTES.items():
            nuevos[clave] = st.number_input(
                etiqueta, min_value=minimo, max_value=maximo, step=1, value=ajustes.valor(clave),
                help=f"Valor del .env: {ajustes.por_defecto(clave)}. Rango permitido: {minimo}-{maximo}.")
        if st.form_submit_button("Guardar configuración", type="primary"):
            for clave, n in nuevos.items():
                if int(n) != ajustes.valor(clave):
                    accion(ajustes.actualizar, usuario, clave, int(n), exito="Configuración actualizada.")
            if "mensaje_exito" in st.session_state:
                st.rerun()


def _eventos(usuario: dict, dias: int):
    df = srv.eventos_seguridad(usuario, dias)
    if df.empty:
        st.info("Sin eventos en el periodo.")
        return
    c = st.columns(4)
    for col, tipo in zip(c, ["LOGIN_FALLIDO", "BLOQUEO", "ACCESO_DENEGADO", "SESION_EXPIRADA"]):
        col.metric(tipo.replace("_", " ").capitalize(), int((df["tipo"] == tipo).sum()))
    diario = df.assign(dia=df["fecha"].dt.date).groupby(["dia", "tipo"], as_index=False).size()
    fig = px.bar(diario, x="dia", y="size", color="tipo", labels={"size": "eventos", "dia": ""})
    fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), legend_title_text="")
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.dataframe(df, hide_index=True, width="stretch")
    descargas(df, "eventos_seguridad", "seg")
