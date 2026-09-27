"""
Sistema de diseño de la aplicación.

Dirección visual: instrumento clínico, no panel corporativo. La referencia es el
carro de paro físico — chapa gris, rojo señalético, cajones numerados y etiquetas
de lote impresas en monoespaciada.

Tipografías: IBM Plex Sans (discurso) e IBM Plex Mono (SOLO datos reales: códigos
de carro, lotes, fechas, cantidades — tal como aparecen en la etiqueta de la
ampolla). Ambas con licencia SIL Open Font License 1.1 (ver docs/LICENCIAS.md).

Regla de la monoespaciada: sirve para alinear dígitos y para identificadores que
se leen carácter a carácter. Un rótulo como «opcional» o el pie de una figura van
en sans; ponerlos en mono sería disfraz, no información.
"""

# --- Paleta --------------------------------------------------------------
PAPEL = "#F2F3F1"        # gris frío de sala, fondo general
PAPEL_HUNDIDO = "#E6E8E5"
SUPERFICIE = "#FFFFFF"
TINTA = "#12171C"        # gris de carcasa de equipo médico
TINTA_SUAVE = "#5A6167"
ACERO = "#656C73"        # texto terciario; oscurecido hasta cumplir contraste AA sobre el papel
LINEA = "#D4D7D2"

CARRO = "#C1121F"        # rojo señalético del carro de paro
CARRO_HUNDIDO = "#8E0D17"
MONITOR = "#0F766E"      # verde azulado del trazado del monitor
AMBAR = "#B45309"        # vencimiento próximo (texto y bordes)
AMBAR_FONDO = "#F0B357"  # el mismo aviso como superficie: pide texto oscuro
AMBAR_TEXTO = "#5C3200"
GRAFITO = "#3D444B"

# Estados del inventario (se usan en tablas y semáforos)
COLORES = {
    "ambar_fondo": AMBAR_FONDO,
    "ambar_texto": AMBAR_TEXTO,
    "vigente": MONITOR,
    "proximo_a_vencer": AMBAR,
    "vencido": CARRO,
    "agotado": ACERO,
    "dado_de_baja": "#6B7280",
    "ALTA": CARRO,
    "MEDIA": AMBAR,
    "BAJA": MONITOR,
    "tinta": TINTA,
    "azul": GRAFITO,
    "rojo_carro": CARRO,
}

# Serie para gráficos (contraste suficiente entre sí y en impresión)
SERIE = [GRAFITO, CARRO, MONITOR, AMBAR, "#6D28D9", "#0369A1", ACERO]

FUENTES = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600"
           "&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap")

# --- CSS base compartido por toda la aplicación ---------------------------
BASE = f"""
@import url('{FUENTES}');

:root {{
  --papel: {PAPEL};
  --papel-hundido: {PAPEL_HUNDIDO};
  --superficie: {SUPERFICIE};
  --tinta: {TINTA};
  --tinta-suave: {TINTA_SUAVE};
  --acero: {ACERO};
  --linea: {LINEA};
  --carro: {CARRO};
  --carro-hundido: {CARRO_HUNDIDO};
  --monitor: {MONITOR};
  --ambar: {AMBAR};
  --grafito: {GRAFITO};
  --sans: 'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --mono: 'IBM Plex Mono', ui-monospace, 'Cascadia Mono', monospace;
}}

/* Los iconos de Streamlit son ligaduras tipográficas: conservan su propia fuente */
span[class*="e1ocqwht"], [data-testid="stIconMaterial"], .material-symbols-rounded {{
  font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}}

/* Datos —códigos de carro, lotes, cantidades, fechas— en monoespaciada, como en la
   etiqueta de la ampolla. Solo cifras e identificadores: la monoespaciada aquí sirve
   para alinear dígitos, no para dar aire técnico a un texto corriente. */
.dato, .kpi .v, .carro .cod, .sello, .doc-meta {{
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  font-feature-settings: "zero" 1;   /* cero barrado: no se confunde con la O */
}}

h1, h2, h3, h4 {{ letter-spacing: -0.022em; }}

/* --- Superficies que dibuja el navegador -------------------------------
   Selección, cursor de texto, barras de desplazamiento y anillo de foco vienen
   con los colores del sistema operativo y no pertenecen a ninguna paleta. Se
   tematizan aquí una vez para toda la aplicación. */
::selection {{ background: rgba(193, 18, 31, .18); color: {TINTA}; }}
html {{ scrollbar-color: {ACERO} transparent; scrollbar-width: thin; }}
::-webkit-scrollbar {{ width: 11px; height: 11px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{
  background: {ACERO}; border: 3px solid {PAPEL}; border-radius: 99px;
}}
::-webkit-scrollbar-thumb:hover {{ background: {GRAFITO}; }}
::-webkit-scrollbar-corner {{ background: transparent; }}
input, textarea, [contenteditable] {{ caret-color: {CARRO}; }}
a {{ text-underline-offset: .18em; text-decoration-thickness: from-font; }}
li::marker {{ color: {CARRO}; }}
:focus-visible {{ outline: 2px solid {CARRO}; outline-offset: 2px; border-radius: 1px; }}

/* Botón principal: el pulsador de un equipo, no una píldora */
button[data-testid="stBaseButton-primary"],
button[data-testid="stBaseButton-primaryFormSubmit"] {{
  letter-spacing: .01em;
  transition: background .15s ease;
}}
button[data-testid="stBaseButton-secondary"],
button[data-testid="stBaseButton-secondaryFormSubmit"] {{
  background: transparent;
  border-color: var(--linea);
  font-weight: 500;
}}
button[data-testid="stBaseButton-secondary"]:hover {{
  border-color: var(--grafito);
  color: var(--tinta);
}}
/* Dentro de un botón rojo el anillo rojo no se vería: ahí se invierte */
button[data-testid="stBaseButton-primary"]:focus-visible,
button[data-testid="stBaseButton-primaryFormSubmit"]:focus-visible {{
  outline-color: var(--tinta);
}}

@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{ animation: none !important; transition: none !important; }}
}}
"""

# --- CSS de la aplicación interna (tras iniciar sesión) -------------------
APP = """
.block-container { padding-top: 1.6rem; max-width: 1460px; }

/* Encabezado de pantalla: regla roja y subtítulo alineado a la línea base */
.cabecera {
  display: flex; align-items: baseline; gap: .85rem; flex-wrap: wrap;
  border-bottom: 2px solid var(--carro);
  padding-bottom: .45rem; margin-bottom: 1.3rem;
}
.cabecera .titulo { font-size: 1.72rem; font-weight: 600; line-height: 1.12; letter-spacing: -.028em; }
.cabecera span { color: var(--tinta-suave); font-size: .95rem; }

/* Indicador: una regla superior gruesa codifica el estado; nada de tarjetas iguales */
.kpi {
  background: var(--superficie);
  border: 1px solid var(--linea);
  border-top: 3px solid var(--c, var(--grafito));
  padding: .75rem .9rem .8rem; height: 100%;
}
.kpi .t { font-size: .8rem; color: var(--tinta-suave); line-height: 1.35; }
.kpi .v { font-family: var(--mono); font-size: 1.5rem; font-weight: 600; line-height: 1.15;
          margin-top: .2rem; letter-spacing: -.02em; }
.kpi .d { font-size: .75rem; color: var(--acero); margin-top: .25rem; line-height: 1.4; }

/* Etiqueta de carro: el bloque del cajón */
.carro {
  padding: .62rem .72rem; margin-bottom: .6rem; min-height: 124px;
  border-radius: 2px; transition: transform .12s ease;
}
.carro:hover { transform: translateY(-2px); }
.carro .cod { font-family: var(--mono); font-weight: 600; font-size: 1rem; letter-spacing: -.02em; }
.carro .srv { font-size: .77rem; opacity: .92; }
.carro .est { font-size: .81rem; margin-top: .38rem; line-height: 1.45; }

/* Encabezado de sección dentro de una pantalla */
.seccion {
  font-size: 1.02rem; font-weight: 600; margin: 1.5rem 0 .2rem;
  padding-bottom: .3rem; border-bottom: 1px solid var(--linea);
}
.seccion + [data-testid="stCaptionContainer"] { margin-top: .35rem; }

.etiqueta-ia {
  display: inline-block; background: var(--papel-hundido); color: var(--grafito);
  border: 1px solid var(--linea); border-radius: 2px;
  padding: .08rem .45rem; font-size: .74rem; font-weight: 500;
}

/* Barra lateral */
[data-testid="stSidebar"] { border-right: 1px solid var(--linea); }
[data-testid="stSidebarUserContent"] { padding-top: 1.2rem; }
.identidad { padding-bottom: .9rem; border-bottom: 1px solid var(--linea); margin-bottom: .95rem; }
.identidad b { display: block; font-size: .94rem; letter-spacing: -.01em; line-height: 1.2;
               white-space: nowrap; }
.identidad span { font-size: .73rem; color: var(--acero); letter-spacing: .04em; text-transform: lowercase; }
.usuario { font-size: 1rem; font-weight: 500; line-height: 1.25; margin-bottom: .9rem; }
.usuario span { display: block; font-size: .81rem; font-weight: 400; color: var(--tinta-suave); margin-top: .1rem; }
.pie-lateral { border-top: 1px solid var(--linea); margin: 1.1rem 0 .9rem; }
[data-testid="stSidebar"] [role="radiogroup"] label { padding: .1rem 0; }

/* Tablas: sin sombra ni bordes redondeados */
[data-testid="stDataFrame"] { border: 1px solid var(--linea); }

/* Pestañas: subrayado, no cápsulas */
[data-testid="stTabs"] [data-baseweb="tab-list"] { gap: 1.4rem; border-bottom: 1px solid var(--linea); }
[data-testid="stTabs"] [data-baseweb="tab"] { padding-left: 0; padding-right: 0; }

/* Documentos legales dentro de la aplicación */
.documento h2 { font-size: 1.1rem; margin: 1.9rem 0 .5rem; padding-top: .85rem; border-top: 1px solid var(--linea); }
.documento h3 { font-size: .97rem; margin: 1.2rem 0 .3rem; }
.documento p, .documento li { font-size: .94rem; line-height: 1.75; color: var(--tinta-suave); max-width: 74ch; }
.documento strong { color: var(--tinta); }
.documento table { width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: .9rem; }
.documento th { text-align: left; font-size: .81rem; color: var(--tinta-suave);
                border-bottom: 1px solid var(--tinta); padding: 0 .8rem .4rem 0; }
.documento td { padding: .5rem .8rem .5rem 0; border-bottom: 1px solid var(--linea);
                vertical-align: top; color: var(--tinta-suave); }
"""
