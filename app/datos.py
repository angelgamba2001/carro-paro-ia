"""
Capa de lectura con memoria intermedia para la interfaz.

Streamlit vuelve a ejecutar el script completo ante cada clic, así que sin esta
capa una simple selección en un filtro repetiría todas las consultas de la
pantalla. Aquí se guardan los resultados unos segundos.

Regla: solo se cachean LECTURAS. Cualquier escritura pasa por los servicios y
llama a `refrescar()`, de modo que el inventario que se ve después de registrar
un lote es siempre el real y no una copia antigua.

El parámetro `_usuario` lleva guion bajo para que Streamlit no intente calcular
su huella (es un diccionario). La identidad entra en la clave a través de `firma`,
que incluye el rol: dos personas con permisos distintos no comparten resultados.
"""
import streamlit as st

from src.analitica.kpis import kpis_analiticos, kpis_operativos
from src.analitica.prediccion import leer_metricas
from src.bigdata.procesamiento import leer_gold, ultima_ejecucion
from src.servicios import alertas as srv_alertas
from src.servicios import catalogo as srv_cat
from src.servicios import inventario as srv_inv

SEGUNDOS = 20          # datos operativos: se renuevan solos en menos de medio minuto
SEGUNDOS_LARGO = 300   # resultados del procesamiento: cambian al ejecutar el pipeline


def firma(usuario: dict) -> tuple:
    return usuario["id"], usuario["rol"]


def refrescar():
    """Descarta lo guardado. Se llama después de cada operación que modifica datos."""
    st.cache_data.clear()


# --- Operativo (MySQL) -----------------------------------------------------
@st.cache_data(ttl=SEGUNDOS, show_spinner=False)
def kpis(_usuario, _f):
    return kpis_operativos()


@st.cache_data(ttl=SEGUNDOS, show_spinner=False)
def stock(_usuario, _f):
    return srv_inv.stock_por_carro(_usuario)


@st.cache_data(ttl=SEGUNDOS, show_spinner=False)
def inventario(_usuario, _f, carro_id=None, servicio=None, estados=None, medicamento_id=None,
               incluir_inactivos=False):
    return srv_inv.listar_inventario(_usuario, carro_id, servicio, list(estados) if estados else None,
                                     medicamento_id, incluir_inactivos)


@st.cache_data(ttl=SEGUNDOS, show_spinner=False)
def alertas(_usuario, _f, solo_pendientes=True, tipos=None, carro_id=None):
    return srv_alertas.listar_alertas(_usuario, solo_pendientes, list(tipos) if tipos else None, carro_id)


@st.cache_data(ttl=SEGUNDOS_LARGO, show_spinner=False)
def carros(_f=None):
    return srv_inv.listar_carros()


@st.cache_data(ttl=SEGUNDOS_LARGO, show_spinner=False)
def servicios(_f=None):
    return srv_inv.listar_servicios()


@st.cache_data(ttl=SEGUNDOS, show_spinner=False)
def medicamentos(_f=None):
    return srv_cat.listar_medicamentos()


@st.cache_data(ttl=SEGUNDOS, show_spinner=False)
def catalogo_df(_f=None):
    return srv_cat.catalogo_df()


# --- Resultados del procesamiento (archivos Parquet) -----------------------
@st.cache_data(ttl=SEGUNDOS_LARGO, show_spinner=False)
def gold(nombre: str):
    return leer_gold(nombre)


@st.cache_data(ttl=SEGUNDOS_LARGO, show_spinner=False)
def kpis_historicos(_f=None):
    return kpis_analiticos()


@st.cache_data(ttl=SEGUNDOS_LARGO, show_spinner=False)
def metricas_modelo(_f=None):
    return leer_metricas()


@st.cache_data(ttl=SEGUNDOS_LARGO, show_spinner=False)
def ejecucion_pipeline(_f=None):
    return ultima_ejecucion()
