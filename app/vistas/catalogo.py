import streamlit as st

from app.componentes import accion, cabecera
from src.servicios import catalogo as srv


def mostrar(usuario: dict):
    cabecera("Catálogo", "Medicamentos de la dotación y sus parámetros de stock")
    df = srv.catalogo_df()
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"costo_unitario": st.column_config.NumberColumn("costo (COP)", format="%.0f")})
    izq, der = st.columns(2)
    with izq:
        st.markdown("#### Nuevo medicamento")
        with st.form("nuevo_med"):
            nombre = st.text_input("Nombre y concentración", placeholder="Ej.: Vasopresina 20UI/ml")
            pa = st.text_input("Principio activo")
            cum = st.text_input("Código CUM (opcional)")
            c1, c2, c3, c4 = st.columns(4)
            crit = c1.selectbox("Criticidad", ["ALTA", "MEDIA", "BAJA"])
            mn = c2.number_input("Mínimo", 0, 100, 2)
            mx = c3.number_input("Máximo", 0, 200, 4)
            costo = c4.number_input("Costo", 0.0, 10_000_000.0, 0.0, step=100.0)
            desc = st.text_area("Indicación / descripción", max_chars=500)
            if st.form_submit_button("Agregar", type="primary"):
                accion(srv.crear_medicamento, usuario, nombre, pa, crit, int(mn), int(mx), float(costo), desc, cum,
                       exito=f"'{nombre}' agregado al catálogo.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
    with der:
        st.markdown("#### Ajustar parámetros")
        opciones = {r.nombre: r for r in df.itertuples()}
        sel = st.selectbox("Medicamento", list(opciones))
        m = opciones[sel]
        with st.form("editar_med"):
            c1, c2, c3 = st.columns(3)
            mn = c1.number_input("Mínimo", 0, 100, int(m.stock_minimo))
            mx = c2.number_input("Máximo", 0, 200, int(m.stock_maximo))
            costo = c3.number_input("Costo", 0.0, 10_000_000.0, float(m.costo_unitario), step=100.0)
            activo = st.checkbox("Activo en la dotación", value=bool(m.activo))
            if st.form_submit_button("Guardar"):
                accion(srv.actualizar_parametros, usuario, int(m.id), int(mn), int(mx), float(costo), activo,
                       exito="Parámetros actualizados.")
                if "mensaje_exito" in st.session_state:
                    st.rerun()
