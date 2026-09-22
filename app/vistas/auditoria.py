import plotly.express as px
import streamlit as st

from app.componentes import cabecera, descargas
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
    for nombre, tab in zip(pestañas, st.tabs(pestañas)):
        with tab:
            if nombre == "Log de auditoría":
                df = srv.log_auditoria(usuario, dias)
                if df.empty:
                    st.info("Sin registros en el periodo.")
                    continue
                c1, c2 = st.columns(2)
                acciones = c1.multiselect("Acción", sorted(df["accion"].unique()))
                origenes = c2.multiselect("Origen", sorted(df["origen"].unique()))
                if acciones:
                    df = df[df["accion"].isin(acciones)]
                if origenes:
                    df = df[df["origen"].isin(origenes)]
                st.dataframe(df, hide_index=True, width="stretch")
                descargas(df, "auditoria", "aud")
            else:
                df = srv.eventos_seguridad(usuario, dias)
                if df.empty:
                    st.info("Sin eventos en el periodo.")
                    continue
                c = st.columns(4)
                for col, tipo in zip(c, ["LOGIN_FALLIDO", "BLOQUEO", "ACCESO_DENEGADO", "SESION_EXPIRADA"]):
                    col.metric(tipo.replace("_", " ").capitalize(), int((df["tipo"] == tipo).sum()))
                diario = df.assign(dia=df["fecha"].dt.date).groupby(["dia", "tipo"], as_index=False).size()
                fig = px.bar(diario, x="dia", y="size", color="tipo", labels={"size": "eventos", "dia": ""})
                fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), legend_title_text="")
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
                st.dataframe(df, hide_index=True, width="stretch")
                descargas(df, "eventos_seguridad", "seg")
