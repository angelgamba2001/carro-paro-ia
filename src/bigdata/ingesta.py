"""
Capa de INGESTA (fuentes -> zona RAW). Tres fuentes heterogéneas:

  1. Base operativa MySQL  (inventario, movimientos, catálogo, carros)  -> CSV
  2. Histórico legado      (revisiones, consumos, bajas; varios años)    -> CSV particionado por año
  3. Datos abiertos        (Código Único de Medicamentos - datos.gov.co) -> JSON vía API REST

Cada ejecución deja un manifiesto con lo que se ingirió.
"""
import json
import logging
import shutil
import urllib.parse
import urllib.request
from datetime import datetime

from src import config
from src.database.connection import consultar_df
from src.datos_referencia import MEDICAMENTOS

log = logging.getLogger(__name__)

_TABLAS_OPERATIVAS = {
    "movimientos": """SELECT mv.id, mv.fecha, c.codigo AS carro, s.nombre AS servicio, m.nombre AS medicamento,
                             mv.cantidad, mv.tipo, mv.evento_codigo_azul, mv.motivo
                      FROM movimientos mv JOIN carros c ON c.id = mv.carro_id
                      JOIN servicios s ON s.id = c.servicio_id JOIN cat_medicamentos m ON m.id = mv.medicamento_id""",
    "inventario": """SELECT i.id, c.codigo AS carro, m.nombre AS medicamento, i.lote, i.cantidad,
                            i.fecha_vencimiento, i.estado FROM inventario_carro i
                     JOIN carros c ON c.id = i.carro_id JOIN cat_medicamentos m ON m.id = i.medicamento_id""",
    "catalogo": """SELECT id, nombre, principio_activo, criticidad, stock_minimo, stock_maximo, costo_unitario
                   FROM cat_medicamentos""",
    "carros": """SELECT c.id, c.codigo, s.nombre AS servicio FROM carros c JOIN servicios s ON s.id = c.servicio_id""",
}


def exportar_operativo(sello: str) -> dict:
    destino = config.RAW_DIR / "operativo" / f"corte={sello}"
    destino.mkdir(parents=True, exist_ok=True)
    conteo = {}
    for tabla, sql in _TABLAS_OPERATIVAS.items():
        df = consultar_df(sql)
        df.to_csv(destino / f"{tabla}.csv", index=False)
        conteo[tabla] = len(df)
    return {"ruta": str(destino), "filas": conteo}


def descargar_cum(sello: str, timeout: int = 20) -> dict:
    """Consulta el CUM en datos.gov.co filtrando por los principios activos del carro.
    Si no hay red o la API cambia, usa la muestra local (data/referencia) y lo informa."""
    destino = config.RAW_DIR / "cum"
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"cum_{sello}.json"
    principios = sorted({pa.upper() for _n, pa, *_ in MEDICAMENTOS})
    filtro = " OR ".join(f"upper(principioactivo) like '%{p.split()[0]}%'" for p in principios)
    url = config.CUM_API_URL + "?" + urllib.parse.urlencode({"$limit": 20000, "$where": filtro})
    try:
        # Bandit B310: urlopen admite esquemas como file:// o ftp://, con los que una
        # CUM_API_URL alterada por configuracion podria leer archivos locales. Se exige
        # https antes de abrir la conexion; si falla, el except de abajo usa la muestra local.
        if urllib.parse.urlparse(url).scheme != "https":
            raise ValueError("CUM_API_URL debe usar el esquema https")
        with urllib.request.urlopen(url, timeout=timeout) as r:  # nosec B310 - esquema validado
            datos = json.loads(r.read().decode("utf-8"))
        if not isinstance(datos, list) or not datos:
            raise ValueError("Respuesta vacía o con formato inesperado")
        archivo.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
        return {"origen": "API datos.gov.co", "registros": len(datos), "ruta": str(archivo)}
    except Exception as e:
        log.warning("CUM no disponible por API (%s); se usa muestra local.", e)
        muestra = config.REFERENCIA_DIR / "cum_muestra.json"
        shutil.copy(muestra, archivo)
        n = len(json.loads(muestra.read_text(encoding="utf-8")))
        return {"origen": f"muestra local ({type(e).__name__})", "registros": n, "ruta": str(archivo)}


def inventario_raw() -> dict:
    """Describe el histórico legado disponible en RAW (lo genera scripts/generar_historico.py)."""
    info = {}
    for nombre in ("revisiones", "consumos", "bajas"):
        archivos = list((config.RAW_DIR / nombre).rglob("*.csv"))
        info[nombre] = {"archivos": len(archivos),
                        "mb": round(sum(a.stat().st_size for a in archivos) / 1e6, 1)}
    return info


def ejecutar_ingesta() -> dict:
    sello = datetime.now().strftime("%Y%m%d_%H%M%S")
    manifiesto = {
        "sello": sello,
        "operativo": exportar_operativo(sello),
        "cum": descargar_cum(sello),
        "historico": inventario_raw(),
    }
    (config.RAW_DIR / "manifiestos").mkdir(parents=True, exist_ok=True)
    (config.RAW_DIR / "manifiestos" / f"ingesta_{sello}.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifiesto
