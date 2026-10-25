"""Conexión a MySQL con pool y utilidades de consulta parametrizada."""
import logging
import os
import time
from contextlib import contextmanager
from decimal import Decimal

import mysql.connector
import pandas as pd
from mysql.connector import Error, errors, pooling

from src import config

log = logging.getLogger(__name__)
_pool = None

# Hallazgo DAST-01 (OWASP ZAP, CWE-400). Con 8 conexiones y get_connection() sin
# espera, el escaneo activo agoto el pool y la excepcion escapaba como HTTP 500.
# Se amplia el pool y se reintenta brevemente; si aun asi no hay conexion libre se
# lanza PoolAgotado, que la API traduce a un 503 con Retry-After en vez de un 500.
TAM_POOL = int(os.getenv("DB_POOL_SIZE", "16"))
_ESPERAS = (0.05, 0.15, 0.35)


class PoolAgotado(RuntimeError):
    """No quedo ninguna conexion libre tras agotar los reintentos."""


def _obtener_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="carro_paro",
            pool_size=TAM_POOL,
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
    return _pool


def _tomar_conexion():
    """Conexion del pool, con reintentos cortos si esta momentaneamente agotado."""
    pool = _obtener_pool()
    for espera in _ESPERAS:
        try:
            return pool.get_connection()
        except errors.PoolError:
            time.sleep(espera)
    try:
        return pool.get_connection()
    except errors.PoolError as e:
        log.error("Pool de conexiones agotado (%s configuradas)", TAM_POOL)
        raise PoolAgotado("La base de datos esta atendiendo el maximo de solicitudes "
                          "simultaneas. Reintente en unos segundos.") from e


def obtener_conexion():
    """Compatibilidad con el código v1: retorna una conexión o None.
    Sin usos en el proyecto; se conserva por compatibilidad y pasa por el mismo
    control de pool que conexion()."""
    try:
        return _tomar_conexion()
    except (Error, PoolAgotado) as e:
        log.error("Error al conectar a MySQL: %s", e)
        return None


@contextmanager
def conexion():
    """Uso: with conexion() as conn: ...  (hace commit o rollback automáticamente)."""
    conn = _tomar_conexion()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def consultar(sql: str, params: tuple = (), uno: bool = False):
    """SELECT parametrizado -> lista de dicts (o un dict si uno=True)."""
    with conexion() as conn:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        filas = cur.fetchone() if uno else cur.fetchall()
        cur.close()
        return filas


def consultar_df(sql: str, params: tuple = ()) -> pd.DataFrame:
    """SELECT -> DataFrame. Convierte DECIMAL de MySQL a float para poder operar con pandas/numpy."""
    df = pd.DataFrame(consultar(sql, params))
    for col in df.columns:
        if df[col].dtype == object and df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].astype(float)
    return df


def ejecutar(sql: str, params: tuple = ()) -> int:
    """INSERT/UPDATE/DELETE parametrizado. Retorna lastrowid (o filas afectadas si no hay id)."""
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        resultado = cur.lastrowid or cur.rowcount
        cur.close()
        return resultado


def base_disponible() -> bool:
    try:
        consultar("SELECT 1 AS ok", uno=True)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    print("Conexión OK" if base_disponible() else "No fue posible conectar")
