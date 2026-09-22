import plotly.express as px
import streamlit as st

from app.componentes import COLORES, accion, cabecera, descargas
from src.seguridad.permisos import tiene_permiso
from src.servicios import alertas as srv


def mostrar(usuario: dict):
    cabecera("Alertas", "Vencimientos, faltantes, predicciones, anomalías y recomendaciones del agente")
    c1, c2 = st.columns([2, 1])
    tipos = c1.multiselect("Tipo", srv.TIPOS)
    pendientes = c2.toggle("Solo pendientes", value=True)
    df = srv.listar_alertas(usuario, solo_pendientes=pendientes, tipos=tipos or None)
    if df.empty:
        st.success("No hay alertas con esos filtros.")
        return
    izq, der = st.columns([1, 2])
    with izq:
        conteo = df.groupby(["tipo", "severidad"], as_index=False).size()
        fig = px.bar(conteo, x="size", y="tipo", color="severidad", orientation="h",
                     color_discrete_map=COLORES, labels={"size": "alertas", "tipo": ""})
        fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0), legend_title_text="")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    with der:
        st.dataframe(df.drop(columns=["atendida"]), hide_index=True, width="stretch", height=280)
    descargas(df, "alertas", "al")

    if tiene_permiso(usuario, "alertas.gestionar"):
        pend = df[df["atendida"] == 0]
        if pend.empty:
            return
        st.markdown("#### Atender alerta")
        opciones = {f"#{r.id} · {r.tipo} · {r.carro or ''} {r.medicamento or ''} · {r.mensaje}": r.id
                    for r in pend.itertuples()}
        with st.form("atender"):
            sel = st.selectbox("Alerta", list(opciones))
            nota = st.text_input("Acción realizada", max_chars=255, placeholder="Ej.: se repusieron 4 ampollas")
            if st.form_submit_button("Marcar como atendida", type="primary"):
                accion(srv.atender_alerta, usuario, opciones[sel], nota, exito="Alerta atendida.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
