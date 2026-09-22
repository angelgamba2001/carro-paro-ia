"""Conexión a MySQL con pool y utilidades de consulta parametrizada."""
import logging
from contextlib import contextmanager
from decimal import Decimal

import mysql.connector
import pandas as pd
from mysql.connector import Error, pooling

from src import config

log = logging.getLogger(__name__)
_pool = None


def _obtener_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="carro_paro",
            pool_size=8,
            host=config.DB_HOST,
            port=config.DB_PORT,
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            database=config.DB_NAME,
            charset="utf8mb4",
            collation="utf8mb4_unicode_ci",
        )
    return _pool


def obtener_conexion():
    """Compatibilidad con el código v1: retorna una conexión o None."""
    try:
        return _obtener_pool().get_connection()
    except Error as e:
        log.error("Error al conectar a MySQL: %s", e)
        return None


@contextmanager
def conexion():
    """Uso: with conexion() as conn: ...  (hace commit o rollback automáticamente)."""
    conn = _obtener_pool().get_connection()
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
