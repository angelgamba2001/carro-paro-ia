"""Dashboard: pestaña operativa (tiempo real, MySQL) y analítica (histórico procesado, GOLD)."""
import pandas as pd
import plotly.express as px
import streamlit as st

from app import datos
from app import asistente_tablero
from app.componentes import (COLORES, SERIE, cabecera, kpi, leyenda_colores, moneda, numero,
                              seccion)
from src.seguridad.permisos import tiene_permiso

_LAYOUT = dict(
    margin=dict(l=8, r=8, t=44, b=8),
    font=dict(color=COLORES["tinta"], family="IBM Plex Sans, system-ui, sans-serif", size=12),
    title=dict(font=dict(size=15, color=COLORES["tinta"])),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    legend_title_text="", legend=dict(font=dict(size=11)),
    hoverlabel=dict(font=dict(family="IBM Plex Sans, system-ui, sans-serif", size=12)),
    separators=",.",          # formato colombiano: 1.234,5
)


def _fig(fig, alto=340):
    """Aplica el estilo común: rejilla discreta, sin títulos de eje heredados del nombre de columna."""
    fig.update_layout(height=alto, **_LAYOUT)
    fig.update_xaxes(showgrid=False, title_text="", linecolor="#D4D7D2", ticks="outside",
                     tickcolor="#D4D7D2", tickfont=dict(size=11, color="#5A6167"))
    fig.update_yaxes(gridcolor="#E6E8E5", zeroline=False, linecolor="rgba(0,0,0,0)",
                     tickfont=dict(size=11, color="#5A6167"))
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def mostrar(usuario: dict):
    cabecera("Tablero", "Estado de los carros de paro")
    leyenda_colores()
    pestañas = ["Operativo"]
    if tiene_permiso(usuario, "dashboard.analitico"):
        pestañas.append("Analítico")
    tabs = st.tabs(pestañas)
    with tabs[0]:
        _operativo(usuario)
    if len(tabs) > 1:
        with tabs[1]:
            _analitico(usuario)
    asistente_tablero.mostrar(usuario)


# ---------------------------------------------------------------------------
@st.fragment
def _operativo(usuario):
    f = datos.firma(usuario)
    k = datos.kpis(usuario, f)
    c = st.columns(6)
    kpi(c[0], "Carros completos", f"{k['carros_completos']}/{k['total_carros']}",
f"{numero(k['disponibilidad_pct'])} % con los medicamentos críticos completos",
        COLORES["vigente"] if k["disponibilidad_pct"] >= 90 else COLORES["vencido"])
    kpi(c[1], "Unidades vencidas", k["unidades_vencidas"], "deben retirarse del carro",
        COLORES["vencido"] if k["unidades_vencidas"] else COLORES["vigente"])
    kpi(c[2], "Próximas a vencer", k["unidades_proximas"], "en los próximos 30 días", COLORES["proximo_a_vencer"])
    kpi(c[3], "Valor en riesgo", moneda(k["valor_en_riesgo"], compacta=True),
        f"{moneda(k['valor_en_riesgo'])} vencido + por vencer", COLORES["rojo_carro"])
    kpi(c[4], "Alertas pendientes", k["alertas_pendientes"], f"{k['alertas_altas']} de severidad alta",
        COLORES["ALTA"] if k["alertas_altas"] else COLORES["azul"])
    var = k["variacion_consumo_pct"]
    kpi(c[5], "Consumo 30 días", k["consumo_30d"],
        f"{numero(var, signo=True)} % frente a los 30 días previos, con "
        f"{k['eventos_codigo_azul_30d']} códigos azules"
        if var is not None
        else f"{k['eventos_codigo_azul_30d']} códigos azules")

    stock = datos.stock(usuario, f)
    inv = datos.inventario(usuario, f)
    servicios = ["Todos"] + sorted(stock["servicio"].unique())
    filtro = st.selectbox("Servicio", servicios, key="tab_op_servicio")
    if filtro != "Todos":
        stock = stock[stock["servicio"] == filtro]
        inv = inv[inv["servicio"] == filtro]

    seccion("Semáforo de carros")
    st.caption("En rojo, los carros a los que les falta un medicamento crítico o tienen lotes vencidos. "
               "En ámbar, faltantes no críticos o lotes por vencer. En verde, completos y vigentes.")
    _semaforo(stock, inv)

    izq, der = st.columns([1.35, 1])
    with izq:
        seccion("Cobertura de dotación por carro")
        s = stock.assign(cobertura=(stock["stock"] / stock["stock_minimo"]).clip(upper=2).round(2))
        matriz = s.pivot_table(index="medicamento", columns="carro", values="cobertura")
        # La dotación completa se deja en calma; el ojo debe ir a los huecos.
        fig = px.imshow(matriz, color_continuous_scale=[[0, COLORES["vencido"]], [0.24, "#E4707A"],
                                                        [0.49, "#F6C9A8"], [0.5, "#EDEEEA"],
                                                        [1, "#C9D8D4"]],
                        zmin=0, zmax=2, aspect="auto",
                        labels=dict(color="stock / mínimo"))
        fig.update_xaxes(side="top", title=None)
        fig.update_yaxes(title=None)
        _fig(fig, alto=520)
    with der:
        seccion("Próximos vencimientos")
        prox = inv[inv["dias_para_vencer"] <= 60].sort_values("dias_para_vencer")
        st.dataframe(prox[["carro", "medicamento", "lote", "cantidad", "dias_para_vencer"]], hide_index=True,
                     width="stretch", height=250,
                     column_config={"dias_para_vencer": st.column_config.NumberColumn("días", format="%d")})
        seccion("Estado de las unidades")
        por_estado = inv.groupby("estado", as_index=False)["cantidad"].sum()
        fig = px.bar(por_estado, x="cantidad", y="estado", orientation="h", color="estado",
                     color_discrete_map=COLORES, text="cantidad")
        fig.update_layout(showlegend=False)
        fig.update_yaxes(title=None)
        _fig(fig, alto=200)


def _semaforo(stock: pd.DataFrame, inv: pd.DataFrame):
    vencidos = inv[inv["estado"] == "vencido"].groupby("carro")["cantidad"].sum()
    proximos = inv[inv["estado"] == "proximo_a_vencer"].groupby("carro")["cantidad"].sum()
    carros = stock.groupby(["carro", "servicio"])
    columnas = st.columns(6)
    for i, ((carro, servicio), g) in enumerate(carros):
        faltan_crit = g[(g["stock"] < g["stock_minimo"]) & (g["criticidad"] == "ALTA")]
        faltan = g[g["stock"] < g["stock_minimo"]]
        v, p = int(vencidos.get(carro, 0)), int(proximos.get(carro, 0))
        # El aviso ámbar va sobre superficie clara para no confundirse con el rojo
        if len(faltan_crit) or v:
            color, texto, estado = COLORES["vencido"], "#FFFFFF", []
        elif len(faltan) or p:
            color, texto, estado = COLORES["ambar_fondo"], COLORES["ambar_texto"], []
        else:
            color, texto, estado = COLORES["vigente"], "#FFFFFF", ["Completo y vigente"]
        if len(faltan):
            estado.append(f"{len(faltan)} faltante{'s' if len(faltan) > 1 else ''} "
                          f"({len(faltan_crit)} crítico{'s' if len(faltan_crit) != 1 else ''})")
        if v:
            estado.append(f"{v} ud vencidas")
        if p:
            estado.append(f"{p} ud por vencer")
        columnas[i % 6].markdown(
            f'<div class="carro" style="background:{color};color:{texto}"><div class="cod">{carro}</div>'
            f'<div class="srv">{servicio}</div><div class="est">{"<br>".join(estado)}</div></div>',
            unsafe_allow_html=True)


# ---------------------------------------------------------------------------
@st.fragment
def _analitico(usuario):
    ejec = datos.ejecucion_pipeline()
    if not ejec:
        st.info("Todavía no hay un procesamiento disponible. El analista de datos o el área de "
                "sistemas pueden ejecutarlo desde la sección Big Data; desde ese momento aparecerán "
                "aquí las tendencias, la predicción de demanda y la matriz de riesgo.")
        return
    marca = ejec["fecha"].replace("T", " a las ")[:-3]
    st.caption(f"Último procesamiento: {marca}, sobre "
               f"{sum(ejec['silver_filas'].values()):,} registros".replace(",", ".") +
               f" (motor {ejec['motor']}).")

    ka, met = datos.kpis_historicos(), datos.metricas_modelo() or {}
    c = st.columns(5)
    kpi(c[0], "Pérdida por vencimiento", moneda(ka.get("perdida_vencimiento_12m"), compacta=True),
        f"{ka.get('unidades_vencidas_12m', 0)} unidades en 12 meses", COLORES["rojo_carro"])
    cumpl = ka.get("cumplimiento_revision_pct", 0)
    kpi(c[1], "Revisión diaria", f"{numero(cumpl)} %",
        f"en el último mes, con {ka.get('discrepancias_ultimo_mes', 0)} discrepancias de conteo",
        COLORES["vigente"] if cumpl >= 95 else COLORES["proximo_a_vencer"])
    var = ka.get("variacion_eventos_anual_pct")
    kpi(c[2], "Códigos azules 12 meses", ka.get("eventos_codigo_azul_12m", 0),
        f"{numero(var, signo=True)} % frente al año anterior" if var is not None else "")
    pred = datos.gold("predicciones")
    en_riesgo = int(pred["riesgo_desabastecimiento"].sum()) if not pred.empty else 0
    kpi(c[3], "Riesgo de desabastecimiento", en_riesgo, f"carro-medicamento en {met.get('horizonte_dias', 14)} días",
        COLORES["ALTA"] if en_riesgo else COLORES["vigente"])
    if met:
        kpi(c[4], "Error del modelo", numero(met["mae_modelo"], 2),
            f"un {numero(met['mejora_vs_base_pct'])} % mejor que la estimación simple")

    diario = datos.gold("consumo_diario")
    diario["fecha"] = pd.to_datetime(diario["fecha"])
    f1, f2, f3 = st.columns([1, 1.4, 1.4])
    servicios = sorted(diario["servicio"].unique())
    sel_serv = f1.multiselect("Servicios", servicios, default=servicios, key="an_serv")
    meds = sorted(diario["medicamento"].unique())
    sel_med = f2.multiselect("Medicamentos", meds, key="an_med", placeholder="Todos")
    minimo, maximo = diario["fecha"].min().date(), diario["fecha"].max().date()
    rango = f3.date_input("Periodo", (max(minimo, maximo.replace(year=maximo.year - 2)), maximo),
                          min_value=minimo, max_value=maximo, key="an_rango")
    d = diario[diario["servicio"].isin(sel_serv)]
    if sel_med:
        d = d[d["medicamento"].isin(sel_med)]
    if isinstance(rango, tuple) and len(rango) == 2:
        d = d[(d["fecha"].dt.date >= rango[0]) & (d["fecha"].dt.date <= rango[1])]
    mes_actual = pd.Timestamp.today().to_period("M").start_time   # el mes en curso está incompleto

    t1, t2, t3, t4 = st.tabs(["Tendencias", "Predicción y riesgo", "Calidad y revisiones", "Anomalías"])
    with t1:
        izq, der = st.columns(2)
        with izq:
            mensual = d.assign(mes=d["fecha"].dt.to_period("M").dt.start_time) \
                       .groupby(["mes", "servicio"], as_index=False)["unidades"].sum() \
                       .query("mes < @mes_actual")
            fig = px.line(mensual, x="mes", y="unidades", color="servicio", color_discrete_sequence=SERIE,
                          title="Consumo mensual por servicio")
            fig.update_yaxes(title_text="unidades")
            fig.update_xaxes(tickformat="%m/%Y")
            _fig(fig)
        with der:
            top = d.groupby("medicamento", as_index=False)["unidades"].sum().nlargest(10, "unidades")
            fig = px.bar(top.sort_values("unidades"), x="unidades", y="medicamento", orientation="h",
                         title="Medicamentos más consumidos", color_discrete_sequence=[COLORES["azul"]])
            fig.update_yaxes(title_text="", gridcolor="rgba(0,0,0,0)")
            _fig(fig)
            fig.update_xaxes(title_text="unidades")
        izq, der = st.columns(2)
        with izq:
            ev = datos.gold("eventos_mensuales")
            ev["mes"] = pd.to_datetime(ev["mes"])
            ev = ev[ev["servicio"].isin(sel_serv) & (ev["mes"] < mes_actual)]
            fig = px.bar(ev, x="mes", y="eventos_codigo_azul", color="servicio",
                         color_discrete_sequence=SERIE, title="Eventos de código azul por mes")
            fig.update_yaxes(title_text="eventos")
            fig.update_xaxes(tickformat="%m/%Y")
            _fig(fig)
        with der:
            bajas = datos.gold("bajas_mensual")
            bajas["mes"] = pd.to_datetime(bajas["mes"])
            bajas = bajas[bajas["servicio"].isin(sel_serv)].groupby("mes", as_index=False)["costo"].sum()
            fig = px.area(bajas, x="mes", y="costo", title="Pérdidas por vencimiento",
                          color_discrete_sequence=[COLORES["rojo_carro"]])
            fig.update_yaxes(title_text="pesos", tickprefix="$", tickformat=",.0f")
            fig.update_xaxes(tickformat="%m/%Y")
            _fig(fig)
        seccion("Comparación de servicios en el periodo elegido")
        comp = d.groupby("servicio").agg(unidades=("unidades", "sum"), eventos=("eventos", "sum"),
                                         dias_con_consumo=("fecha", "nunique")).reset_index()
        comp["unidades_por_evento"] = (comp["unidades"] / comp["eventos"].replace(0, pd.NA)).round(2)
        st.dataframe(comp.sort_values("unidades", ascending=False), hide_index=True, width="stretch")

    with t2:
        if pred.empty:
            st.info("Sin predicciones todavía.")
        else:
            p = pred[pred["servicio"].isin(sel_serv)]
            if sel_med:
                p = p[p["medicamento"].isin(sel_med)]
            riesgo = p[p["riesgo_desabastecimiento"] == 1].sort_values("dias_cobertura")
            st.markdown(f"**{len(riesgo)}** combinaciones quedarían bajo el mínimo en "
                        f"{met.get('horizonte_dias', 14)} días si no se repone.")
            st.dataframe(riesgo[["carro", "servicio", "medicamento", "criticidad", "stock", "demanda_estimada",
                                 "dias_cobertura", "unidades_a_reponer"]], hide_index=True, width="stretch",
                         column_config={"demanda_estimada": st.column_config.NumberColumn("demanda 14 d",
                                                                                          format="%.1f"),
                                        "dias_cobertura": st.column_config.ProgressColumn(
                                            "cobertura (días)", min_value=0, max_value=60, format="%.0f")})
            r = datos.gold("riesgo")
            if not r.empty:
                agrupado = r.groupby(["probabilidad", "impacto", "nivel_riesgo"], as_index=False) \
                            .agg(casos=("carro", "count"))
                fig = px.scatter(agrupado, x="probabilidad", y="impacto", size="casos", color="nivel_riesgo",
                                 color_discrete_map={"ALTO": COLORES["vencido"], "MEDIO": COLORES["MEDIA"],
                                                    "BAJO": COLORES["vigente"]},
                                 title="Matriz de riesgo (probabilidad × impacto)", size_max=45)
                fig.update_xaxes(range=[0.5, 5.5], dtick=1)
                fig.update_yaxes(range=[0.5, 5.5], dtick=1)
                _fig(fig, alto=380)

    with t3:
        rev = datos.gold("revisiones_mensual")
        rev["mes"] = pd.to_datetime(rev["mes"])
        fig = px.line(rev, x="mes", y="cumplimiento_pct", color="carro",
                      title="Cumplimiento de la revisión diaria",
                      color_discrete_sequence=px.colors.qualitative.Safe)
        fig.update_yaxes(title_text="% de días revisados", ticksuffix=" %")
        fig.update_xaxes(tickformat="%m/%Y")
        fig.add_hline(y=95, line_dash="dot", line_color=COLORES["rojo_carro"], annotation_text="meta 95 %")
        _fig(fig)
        seccion("Reglas de limpieza aplicadas")
        st.dataframe(datos.gold("calidad_datos"), hide_index=True, width="stretch")
        seccion("Integración con el catálogo público de medicamentos")
        st.dataframe(datos.gold("catalogo_enriquecido"), hide_index=True, width="stretch")

    with t4:
        an = datos.gold("anomalias")
        if an.empty:
            st.success("No se detectaron consumos anómalos en las últimas 8 semanas.")
        else:
            st.dataframe(an, hide_index=True, width="stretch")

    # Espacio de integración: el agente explica lo que se está viendo
    if tiene_permiso(usuario, "agente.usar"):
        st.divider()
        st.markdown('<span class="etiqueta-ia">Agente IA</span>', unsafe_allow_html=True)
        if st.button("Pedir al agente una interpretación de este tablero"):
            from src.agente.agente import AgenteCarroParo
            with st.spinner("Analizando indicadores..."):
                r = AgenteCarroParo().responder(
                    usuario, "Interpreta los indicadores históricos, el riesgo de desabastecimiento y las "
                             "anomalías, y recomienda acciones")
            st.markdown(r["respuesta"])
