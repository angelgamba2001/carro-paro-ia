from datetime import date, timedelta

import streamlit as st

from app import datos
from app.componentes import accion, cabecera, descargas
from src.seguridad.permisos import tiene_permiso
from src.servicios import inventario as srv_inv

ESTADOS = ["vigente", "proximo_a_vencer", "vencido", "agotado", "dado_de_baja"]


def _etiqueta_lote(r) -> str:
    return f"#{r['id']} · {r['carro']} · {r['medicamento']} · lote {r['lote']} · {r['cantidad']} ud · vence {r['fecha_vencimiento']}"


def mostrar(usuario: dict):
    cabecera("Inventario", "Lotes por carro, consumo y bajas")
    f = datos.firma(usuario)
    carros = datos.carros()
    meds = datos.medicamentos()

    f1, f2, f3, f4 = st.columns(4)
    servicio = f1.selectbox("Servicio", ["Todos"] + datos.servicios())
    carros_f = [c for c in carros if servicio == "Todos" or c["servicio"] == servicio]
    carro = f2.selectbox("Carro", ["Todos"] + [c["codigo"] for c in carros_f])
    estados = f3.multiselect("Estado", ESTADOS, default=["vigente", "proximo_a_vencer", "vencido"])
    med = f4.selectbox("Medicamento", ["Todos"] + [m["nombre"] for m in meds])

    carro_id = next((c["id"] for c in carros if c["codigo"] == carro), None)
    med_id = next((m["id"] for m in meds if m["nombre"] == med), None)
    df = datos.inventario(usuario, f, carro_id=carro_id,
                          servicio=None if servicio == "Todos" else servicio,
                          estados=tuple(estados) if estados else None, medicamento_id=med_id,
                          incluir_inactivos=True)
    st.dataframe(df.drop(columns=["carro_id", "medicamento_id"], errors="ignore"), hide_index=True, width="stretch",
                 column_config={
                     "estado": st.column_config.TextColumn("estado"),
                     "dias_para_vencer": st.column_config.NumberColumn("días p/ vencer", format="%d"),
                     "fecha_registro": st.column_config.DatetimeColumn("registrado", format="YYYY-MM-DD HH:mm"),
                 })
    st.caption(f"{len(df)} lotes · {int(df['cantidad'].sum()) if not df.empty else 0} unidades")
    if not df.empty:
        descargas(df, "inventario", "inv")

    acciones = []
    if tiene_permiso(usuario, "inventario.registrar"):
        acciones.append("Registrar lote")
    if tiene_permiso(usuario, "inventario.consumo"):
        acciones.append("Registrar consumo")
    if tiene_permiso(usuario, "inventario.editar"):
        acciones.append("Corregir lote")
    if tiene_permiso(usuario, "inventario.baja"):
        acciones.append("Dar de baja")
    if not acciones:
        return
    st.divider()
    tabs = st.tabs(acciones)
    activos = datos.inventario(usuario, f, carro_id=carro_id)
    opciones = {_etiqueta_lote(r): r["id"] for _, r in activos.iterrows()}

    for nombre, tab in zip(acciones, tabs):
        with tab:
            if nombre == "Registrar lote":
                _form_registro(usuario, carros, meds)
            elif nombre == "Registrar consumo":
                usables = activos[activos["estado"].isin(["vigente", "proximo_a_vencer"])]
                lotes_ok = {_etiqueta_lote(r): r["id"] for _, r in usables.iterrows()}
                with st.form("consumo"):
                    sel = st.selectbox("Lote", list(lotes_ok) or ["(sin lotes disponibles)"])
                    c1, c2 = st.columns(2)
                    cant = c1.number_input("Unidades usadas", 1, 500, 1)
                    azul = c2.checkbox("Uso en código azul", value=True)
                    motivo = st.text_input("Observación", max_chars=255)
                    if st.form_submit_button("Registrar consumo", type="primary") and lotes_ok:
                        accion(srv_inv.registrar_consumo, usuario, lotes_ok[sel], int(cant), motivo, azul,
                               exito="Consumo registrado.")
                        if "mensaje_exito" in st.session_state:
                            st.rerun()
            elif nombre == "Corregir lote":
                with st.form("editar"):
                    sel = st.selectbox("Registro", list(opciones) or ["(sin registros)"])
                    nuevo = st.text_input("Código de lote correcto", max_chars=60)
                    st.caption("La fecha de vencimiento no se puede modificar: si está mal, dé de baja el "
                               "registro y vuelva a ingresarlo.")
                    if st.form_submit_button("Guardar corrección") and opciones:
                        accion(srv_inv.actualizar_lote, usuario, opciones[sel], nuevo, exito="Lote corregido.")
                        if "mensaje_exito" in st.session_state:
                            st.rerun()
            elif nombre == "Dar de baja":
                with st.form("baja"):
                    sel = st.selectbox("Registro", list(opciones) or ["(sin registros)"])
                    motivo = st.selectbox("Motivo", ["Vencimiento", "Daño / ruptura", "Error de registro",
                                                     "Retiro por alerta sanitaria"])
                    detalle = st.text_input("Detalle (opcional)", max_chars=200)
                    confirmar = st.checkbox("Confirmo que el lote fue retirado físicamente del carro")
                    if st.form_submit_button("Dar de baja", type="primary") and opciones:
                        if not confirmar:
                            st.error("Debe confirmar el retiro físico.")
                        else:
                            accion(srv_inv.dar_de_baja, usuario, opciones[sel], f"{motivo}. {detalle}".strip(),
                                   exito="Lote dado de baja.")
                            if "mensaje_exito" in st.session_state:
                                st.rerun()


def _form_registro(usuario, carros, meds, prefijo: str = "reg", lote_ini: str = "",
                   fecha_ini: date | None = None, origen: str = "MANUAL", confianza: float | None = None):
    with st.form(f"form_{prefijo}"):
        c1, c2 = st.columns(2)
        carro = c1.selectbox("Carro", [f"{c['codigo']} · {c['servicio']}" for c in carros], key=f"{prefijo}_c")
        med = c2.selectbox("Medicamento", [f"{m['nombre']} ({m['criticidad']})" for m in meds], key=f"{prefijo}_m")
        c3, c4, c5 = st.columns(3)
        lote = c3.text_input("Lote", value=lote_ini, max_chars=60, key=f"{prefijo}_l")
        cantidad = c4.number_input("Cantidad", 1, 500, 1, key=f"{prefijo}_q")
        venc = c5.date_input("Vencimiento", value=fecha_ini or date.today() + timedelta(days=365),
                             min_value=date.today() + timedelta(days=1), key=f"{prefijo}_v")
        if st.form_submit_button("Guardar en inventario", type="primary"):
            carro_id = carros[[f"{c['codigo']} · {c['servicio']}" for c in carros].index(carro)]["id"]
            med_id = meds[[f"{m['nombre']} ({m['criticidad']})" for m in meds].index(med)]["id"]
            r = accion(srv_inv.registrar_lote, usuario, carro_id, med_id, lote, int(cantidad), venc,
                       origen=origen, confianza_ocr=confianza, exito=f"Lote {lote.upper()} registrado.")
            if r:
                st.rerun()
