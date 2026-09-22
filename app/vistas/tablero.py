"""Dashboard: pestaña operativa (tiempo real, MySQL) y analítica (histórico procesado, GOLD)."""
import pandas as pd
import plotly.express as px
import streamlit as st

from app.componentes import COLORES, SERIE, cabecera, kpi, moneda
from src.analitica.kpis import kpis_analiticos, kpis_operativos
from src.analitica.prediccion import leer_metricas
from src.bigdata.procesamiento import leer_gold, ultima_ejecucion
from src.seguridad.permisos import tiene_permiso
from src.servicios import inventario as srv_inv

_LAYOUT = dict(margin=dict(l=10, r=10, t=40, b=10), font=dict(color=COLORES["tinta"]),
               paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="")


def _fig(fig, alto=340):
    fig.update_layout(height=alto, **_LAYOUT)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def mostrar(usuario: dict):
    cabecera("Tablero", "Estado de los carros de paro")
    pestañas = ["Operativo"]
    if tiene_permiso(usuario, "dashboard.analitico"):
        pestañas.append("Analítico")
    tabs = st.tabs(pestañas)
    with tabs[0]:
        _operativo(usuario)
    if len(tabs) > 1:
        with tabs[1]:
            _analitico(usuario)


# ---------------------------------------------------------------------------
def _operativo(usuario):
    k = kpis_operativos()
    c = st.columns(6)
    kpi(c[0], "Carros completos", f"{k['carros_completos']}/{k['total_carros']}",
        f"{k['disponibilidad_pct']}% con medicamentos críticos ≥ mínimo",
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
        f"{var:+.1f}% vs 30 días previos · {k['eventos_codigo_azul_30d']} códigos azules" if var is not None
        else f"{k['eventos_codigo_azul_30d']} códigos azules")

    stock = srv_inv.stock_por_carro(usuario)
    inv = srv_inv.listar_inventario(usuario)
    servicios = ["Todos"] + sorted(stock["servicio"].unique())
    filtro = st.selectbox("Servicio", servicios, key="tab_op_servicio")
    if filtro != "Todos":
        stock = stock[stock["servicio"] == filtro]
        inv = inv[inv["servicio"] == filtro]

    st.markdown("#### Semáforo de carros")
    st.caption("Rojo: falta un medicamento crítico o hay lotes vencidos · Ámbar: faltantes no críticos o lotes "
               "por vencer · Verde: completo y vigente")
    _semaforo(stock, inv)

    izq, der = st.columns([1.35, 1])
    with izq:
        st.markdown("#### Cobertura de dotación por carro")
        s = stock.assign(cobertura=(stock["stock"] / stock["stock_minimo"]).clip(upper=2).round(2))
        matriz = s.pivot_table(index="medicamento", columns="carro", values="cobertura")
        fig = px.imshow(matriz, color_continuous_scale=[[0, "#D92D20"], [0.49, "#FEE4E2"], [0.5, "#FEF0C7"],
                                                        [0.75, "#D1FADF"], [1, "#12B76A"]],
                        zmin=0, zmax=2, aspect="auto", labels=dict(color="stock/mín."))
        fig.update_xaxes(side="top", title=None)
        fig.update_yaxes(title=None)
        _fig(fig, alto=520)
    with der:
        st.markdown("#### Próximos vencimientos")
        prox = inv[inv["dias_para_vencer"] <= 60].sort_values("dias_para_vencer")
        st.dataframe(prox[["carro", "medicamento", "lote", "cantidad", "dias_para_vencer"]], hide_index=True,
                     width="stretch", height=250,
                     column_config={"dias_para_vencer": st.column_config.NumberColumn("días", format="%d")})
        st.markdown("#### Estado de las unidades")
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
        if len(faltan_crit) or v:
            color, estado = COLORES["vencido"], []
        elif len(faltan) or p:
            color, estado = COLORES["proximo_a_vencer"], []
        else:
            color, estado = COLORES["vigente"], ["Completo y vigente"]
        if len(faltan):
            estado.append(f"{len(faltan)} faltante{'s' if len(faltan) > 1 else ''} "
                          f"({len(faltan_crit)} crítico{'s' if len(faltan_crit) != 1 else ''})")
        if v:
            estado.append(f"{v} ud vencidas")
        if p:
            estado.append(f"{p} ud por vencer")
        columnas[i % 6].markdown(
            f'<div class="carro" style="background:{color}"><div class="cod">{carro}</div>'
            f'<div class="srv">{servicio}</div><div class="est">{"<br>".join(estado)}</div></div>',
            unsafe_allow_html=True)


# ---------------------------------------------------------------------------
def _analitico(usuario):
    ejec = ultima_ejecucion()
    if not ejec:
        st.info("Aún no se ha ejecutado el pipeline Big Data. Un usuario con rol Analista de datos, TI o "
                "Administrador puede ejecutarlo desde la opción Big Data.")
        return
    st.caption(f"Datos procesados el {ejec['fecha'].replace('T', ' ')} con motor {ejec['motor']} · "
               f"{sum(ejec['silver_filas'].values()):,} registros limpios".replace(",", "."))

    ka, met = kpis_analiticos(), leer_metricas() or {}
    c = st.columns(5)
    kpi(c[0], "Pérdida por vencimiento", moneda(ka.get("perdida_vencimiento_12m"), compacta=True),
        f"{ka.get('unidades_vencidas_12m', 0)} unidades en 12 meses", COLORES["rojo_carro"])
    cumpl = ka.get("cumplimiento_revision_pct", 0)
    kpi(c[1], "Revisión diaria", f"{cumpl}%", f"último mes · {ka.get('discrepancias_ultimo_mes', 0)} discrepancias",
        COLORES["vigente"] if cumpl >= 95 else COLORES["proximo_a_vencer"])
    var = ka.get("variacion_eventos_anual_pct")
    kpi(c[2], "Códigos azules 12 meses", ka.get("eventos_codigo_azul_12m", 0),
        f"{var:+.1f}% vs año anterior" if var is not None else "")
    pred = leer_gold("predicciones")
    en_riesgo = int(pred["riesgo_desabastecimiento"].sum()) if not pred.empty else 0
    kpi(c[3], "Riesgo de desabastecimiento", en_riesgo, f"carro-medicamento en {met.get('horizonte_dias', 14)} días",
        COLORES["ALTA"] if en_riesgo else COLORES["vigente"])
    if met:
        kpi(c[4], "Error del modelo (MAE)", met["mae_modelo"],
            f"línea base {met['mae_linea_base']} · mejora {met['mejora_vs_base_pct']}%")

    diario = leer_gold("consumo_diario")
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
            _fig(fig)
        with der:
            top = d.groupby("medicamento", as_index=False)["unidades"].sum().nlargest(10, "unidades")
            fig = px.bar(top.sort_values("unidades"), x="unidades", y="medicamento", orientation="h",
                         title="Medicamentos más consumidos", color_discrete_sequence=[COLORES["azul"]])
            fig.update_yaxes(title=None)
            _fig(fig)
        izq, der = st.columns(2)
        with izq:
            ev = leer_gold("eventos_mensuales")
            ev["mes"] = pd.to_datetime(ev["mes"])
            ev = ev[ev["servicio"].isin(sel_serv) & (ev["mes"] < mes_actual)]
            fig = px.bar(ev, x="mes", y="eventos_codigo_azul", color="servicio", color_discrete_sequence=SERIE,
                         title="Eventos de código azul por mes")
            _fig(fig)
        with der:
            bajas = leer_gold("bajas_mensual")
            bajas["mes"] = pd.to_datetime(bajas["mes"])
            bajas = bajas[bajas["servicio"].isin(sel_serv)].groupby("mes", as_index=False)["costo"].sum()
            fig = px.area(bajas, x="mes", y="costo", title="Pérdidas por vencimiento (COP)",
                          color_discrete_sequence=[COLORES["rojo_carro"]])
            _fig(fig)
        st.markdown("##### Comparación de servicios (periodo filtrado)")
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
            r = leer_gold("riesgo")
            if not r.empty:
                agrupado = r.groupby(["probabilidad", "impacto", "nivel_riesgo"], as_index=False) \
                            .agg(casos=("carro", "count"))
                fig = px.scatter(agrupado, x="probabilidad", y="impacto", size="casos", color="nivel_riesgo",
                                 color_discrete_map={"ALTO": "#D92D20", "MEDIO": "#F79009", "BAJO": "#12B76A"},
                                 title="Matriz de riesgo (probabilidad × impacto)", size_max=45)
                fig.update_xaxes(range=[0.5, 5.5], dtick=1)
                fig.update_yaxes(range=[0.5, 5.5], dtick=1)
                _fig(fig, alto=380)

    with t3:
        rev = leer_gold("revisiones_mensual")
        rev["mes"] = pd.to_datetime(rev["mes"])
        fig = px.line(rev, x="mes", y="cumplimiento_pct", color="carro", title="Cumplimiento de revisión diaria (%)",
                      color_discrete_sequence=px.colors.qualitative.Safe)
        fig.add_hline(y=95, line_dash="dot", line_color=COLORES["rojo_carro"], annotation_text="meta 95%")
        _fig(fig)
        st.markdown("##### Reglas de limpieza aplicadas en el pipeline")
        st.dataframe(leer_gold("calidad_datos"), hide_index=True, width="stretch")
        st.markdown("##### Integración con datos abiertos (CUM)")
        st.dataframe(leer_gold("catalogo_enriquecido"), hide_index=True, width="stretch")

    with t4:
        an = leer_gold("anomalias")
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
