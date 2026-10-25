import logging

"""Piezas visuales y utilidades compartidas por las vistas."""
import streamlit as st

from src.seguridad.permisos import PermisoDenegado
from src.servicios.errores import ErrorNegocio

from app.estilos import APP, BASE, COLORES, MOVIL, SERIE  # noqa: F401


def estilos():
    st.markdown(f"<style>{BASE}{APP}{MOVIL}</style>", unsafe_allow_html=True)




def cabecera(titulo: str, subtitulo: str = ""):
    st.markdown(f'<div class="cabecera"><div class="titulo">{titulo}</div><span>{subtitulo}</span></div>', unsafe_allow_html=True)


def seccion(texto: str):
    """Encabezado de sección dentro de una pantalla."""
    st.markdown(f'<div class="seccion">{texto}</div>', unsafe_allow_html=True)


def kpi(col, titulo: str, valor, detalle: str = "", color: str = COLORES["azul"]):
    col.markdown(f'<div class="kpi" style="--c:{color}"><div class="t">{titulo}</div>'
                 f'<div class="v">{valor}</div><div class="d">{detalle}</div></div>', unsafe_allow_html=True)


def numero(v, decimales: int = 1, signo: bool = False) -> str:
    """Formato colombiano: coma decimal y punto de miles. 1234.5 -> 1.234,5"""
    if v is None:
        return "—"
    s = f"{v:{'+' if signo else ''},.{decimales}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def moneda(v, compacta: bool = False) -> str:
    """Formato colombiano: $1.235.000 · compacta: $1,2 M"""
    if v is None:
        return "—"
    if compacta and abs(v) >= 1_000_000:
        return f"${numero(v / 1_000_000)} M"
    return f"${numero(v, 0)}"


def accion(fn, *args, exito: str | None = None, **kwargs):
    """Ejecuta una operación de servicio mostrando errores de negocio y de permisos de forma segura.
    Tras una escritura correcta vacía la memoria intermedia: lo que se ve después es el dato real."""
    from app.datos import refrescar
    try:
        r = fn(*args, **kwargs)
        refrescar()
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
    except Exception as e:
        # Bandit B110: sin registro, el usuario no sabia por que faltaba el boton
        # de Excel y el equipo no podia reproducirlo. La descarga CSV sigue activa.
        logging.getLogger(__name__).info("No se ofrece la descarga en Excel: %s", e)
