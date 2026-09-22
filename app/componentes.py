"""Piezas visuales y utilidades compartidas por las vistas."""
import streamlit as st

from src.seguridad.permisos import PermisoDenegado
from src.servicios.errores import ErrorNegocio

COLORES = {
    "vigente": "#12B76A", "proximo_a_vencer": "#F79009", "vencido": "#D92D20",
    "agotado": "#98A2B3", "dado_de_baja": "#667085",
    "ALTA": "#D92D20", "MEDIA": "#F79009", "BAJA": "#1F4E79",
    "tinta": "#1D2939", "azul": "#1F4E79", "rojo_carro": "#B42318",
}
SERIE = ["#1F4E79", "#B42318", "#12B76A", "#F79009", "#7A5AF8", "#0E9384", "#667085"]

CSS = """
<style>
  .block-container {padding-top: 1.6rem; max-width: 1400px;}
  h1, h2, h3 {letter-spacing: -0.01em;}
  .cabecera {display:flex; align-items:baseline; gap:.8rem; border-bottom:3px solid #B42318;
             padding-bottom:.4rem; margin-bottom:1rem;}
  .cabecera .titulo {font-size:1.75rem; font-weight:700; margin:0; color:#1D2939; line-height:1.2;}
  .cabecera span {color:#667085; font-size:.95rem;}
  .kpi {background:#FFFFFF; border:1px solid #E4E7EC; border-left:5px solid var(--c,#1F4E79);
        border-radius:6px; padding:.7rem .9rem; height:100%;}
  .kpi .v {font-size:1.55rem; white-space:nowrap; font-weight:700; color:#1D2939; line-height:1.15;}
  .kpi .t {font-size:.85rem; color:#475467;}
  .kpi .d {font-size:.78rem; color:#667085; margin-top:.2rem;}
  .carro {border-radius:8px; padding:.55rem .7rem; color:#fff; margin-bottom:.6rem; min-height:122px;}
  .carro .cod {font-weight:700; font-size:1.02rem;}
  .carro .srv {font-size:.78rem; opacity:.9;}
  .carro .est {font-size:.82rem; margin-top:.35rem;}
  .etiqueta-ia {display:inline-block; background:#EEF4FF; color:#1F4E79; border:1px solid #C7D7FE;
                border-radius:4px; padding:.05rem .4rem; font-size:.75rem;}
  [data-testid="stSidebar"] {border-right:1px solid #E4E7EC;}
</style>
"""


def estilos():
    st.markdown(CSS, unsafe_allow_html=True)


def cabecera(titulo: str, subtitulo: str = ""):
    st.markdown(f'<div class="cabecera"><div class="titulo">{titulo}</div><span>{subtitulo}</span></div>', unsafe_allow_html=True)


def kpi(col, titulo: str, valor, detalle: str = "", color: str = COLORES["azul"]):
    col.markdown(f'<div class="kpi" style="--c:{color}"><div class="t">{titulo}</div>'
                 f'<div class="v">{valor}</div><div class="d">{detalle}</div></div>', unsafe_allow_html=True)


def moneda(v, compacta: bool = False) -> str:
    """Formato colombiano: $1.235.000 · compacta: $1,2 M"""
    if v is None:
        return "—"
    if compacta and abs(v) >= 1_000_000:
        return f"${v / 1_000_000:,.1f} M".replace(".", ",")
    return f"${v:,.0f}".replace(",", ".")


def accion(fn, *args, exito: str | None = None, **kwargs):
    """Ejecuta una operación de servicio mostrando errores de negocio y de permisos de forma segura."""
    try:
        r = fn(*args, **kwargs)
        if exito:
            st.session_state["mensaje_exito"] = exito
        return r
    except (ErrorNegocio, PermisoDenegado) as e:
        st.error(str(e))
    except Exception:
        import logging
        logging.getLogger("app").exception("Error no controlado")
        st.error("Ocurrió un error inesperado. El evento quedó registrado.")
    return None


def mensaje_pendiente():
    if "mensaje_exito" in st.session_state:
        st.success(st.session_state.pop("mensaje_exito"))


def descargas(df, nombre: str, clave: str):
    from datetime import datetime
    from src.utils.exportador import generar_csv, generar_excel
    c1, c2, _ = st.columns([1, 1, 4])
    sello = datetime.now().strftime("%Y%m%d")
    c1.download_button("Descargar CSV", generar_csv(df), f"{nombre}_{sello}.csv", "text/csv", key=f"csv_{clave}")
    try:
        c2.download_button("Descargar Excel", generar_excel(df), f"{nombre}_{sello}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"xls_{clave}")
    except Exception:
        pass
