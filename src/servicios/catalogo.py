import pandas as pd

from src.database.auditoria import registrar_log
from src.database.connection import consultar, consultar_df, ejecutar
from src.seguridad.permisos import exigir_permiso
from src.servicios.errores import ErrorNegocio


def listar_medicamentos(solo_activos: bool = True) -> list[dict]:
    # Falso positivo B608: los tres fragmentos son literales y lo unico variable
    # es un booleano que elige entre dos de ellos; ninguna entrada del usuario alcanza
    # la consulta. Reescribirla no reduciria ningun riesgo.
    sql = "SELECT * FROM cat_medicamentos" + (" WHERE activo = 1" if solo_activos else "") + " ORDER BY nombre"  # nosec B608
    return consultar(sql)


def catalogo_df() -> pd.DataFrame:
    return consultar_df("SELECT id, nombre, principio_activo, codigo_cum, criticidad, stock_minimo, "
                        "stock_maximo, costo_unitario, activo FROM cat_medicamentos ORDER BY nombre")


def crear_medicamento(usuario: dict, nombre: str, principio_activo: str, criticidad: str,
                      stock_minimo: int, stock_maximo: int, costo_unitario: float,
                      descripcion: str = "", codigo_cum: str = "") -> int:
    exigir_permiso(usuario, "catalogo.gestionar")
    nombre = (nombre or "").strip()
    if not nombre:
        raise ErrorNegocio("El nombre es obligatorio.")
    if criticidad not in ("ALTA", "MEDIA", "BAJA"):
        raise ErrorNegocio("Criticidad inválida.")
    if stock_minimo < 0 or stock_maximo < stock_minimo:
        raise ErrorNegocio("El stock máximo debe ser mayor o igual al mínimo.")
    if consultar("SELECT id FROM cat_medicamentos WHERE nombre = %s", (nombre,), uno=True):
        raise ErrorNegocio(f"'{nombre}' ya existe en el catálogo.")
    nuevo = ejecutar(
        "INSERT INTO cat_medicamentos (nombre, principio_activo, codigo_cum, descripcion, criticidad, "
        "stock_minimo, stock_maximo, costo_unitario) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (nombre, principio_activo, codigo_cum or None, descripcion, criticidad, stock_minimo, stock_maximo,
         costo_unitario))
    registrar_log(usuario["id"], "INSERCION", "cat_medicamentos", nuevo, f"Nuevo medicamento: {nombre}")
    return nuevo


def actualizar_parametros(usuario: dict, med_id: int, stock_minimo: int, stock_maximo: int,
                          costo_unitario: float, activo: bool):
    exigir_permiso(usuario, "catalogo.gestionar")
    if stock_minimo < 0 or stock_maximo < stock_minimo:
        raise ErrorNegocio("El stock máximo debe ser mayor o igual al mínimo.")
    ejecutar("UPDATE cat_medicamentos SET stock_minimo=%s, stock_maximo=%s, costo_unitario=%s, activo=%s "
             "WHERE id=%s", (stock_minimo, stock_maximo, costo_unitario, 1 if activo else 0, med_id))
    registrar_log(usuario["id"], "ACTUALIZACION", "cat_medicamentos", med_id,
                  f"min={stock_minimo} max={stock_maximo} costo={costo_unitario} activo={activo}")
