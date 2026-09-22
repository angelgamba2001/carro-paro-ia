import pandas as pd

from src.database.auditoria import registrar_log
from src.database.connection import consultar, consultar_df, ejecutar
from src.seguridad.permisos import exigir_permiso
from src.servicios.errores import ErrorNegocio

TIPOS = ("PROXIMO_VENCER", "VENCIDO", "STOCK_BAJO", "RIESGO_DESABASTECIMIENTO",
         "CONSUMO_ANOMALO", "RECOMENDACION_AGENTE")


def listar_alertas(usuario: dict, solo_pendientes: bool = True, tipos=None, carro_id=None) -> pd.DataFrame:
    exigir_permiso(usuario, "alertas.ver")
    cond, params = [], []
    if solo_pendientes:
        cond.append("a.atendida = 0")
    if tipos:
        cond.append("a.tipo IN (" + ",".join(["%s"] * len(tipos)) + ")"); params.extend(tipos)
    if carro_id:
        cond.append("a.carro_id = %s"); params.append(carro_id)
    sql = """
        SELECT a.id, a.tipo, a.severidad, a.origen, c.codigo AS carro, m.nombre AS medicamento,
               i.lote, i.fecha_vencimiento, a.mensaje, a.fecha_generada, a.atendida,
               u.nombre AS atendida_por, a.fecha_atencion, a.nota_atencion
        FROM alertas a
        LEFT JOIN carros c ON c.id = a.carro_id
        LEFT JOIN cat_medicamentos m ON m.id = a.medicamento_id
        LEFT JOIN inventario_carro i ON i.id = a.inventario_id
        LEFT JOIN usuarios u ON u.id = a.atendida_por
    """
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    sql += " ORDER BY a.atendida ASC, FIELD(a.severidad,'ALTA','MEDIA','BAJA'), a.fecha_generada DESC"
    return consultar_df(sql, tuple(params))


def atender_alerta(usuario: dict, alerta_id: int, nota: str = "", origen_llamada: str = "WEB"):
    exigir_permiso(usuario, "alertas.gestionar", origen_llamada)
    a = consultar("SELECT id, atendida FROM alertas WHERE id = %s", (alerta_id,), uno=True)
    if not a:
        raise ErrorNegocio(f"No existe la alerta {alerta_id}.")
    if a["atendida"]:
        raise ErrorNegocio("La alerta ya fue atendida.")
    ejecutar("UPDATE alertas SET atendida = 1, atendida_por = %s, fecha_atencion = NOW(), nota_atencion = %s "
             "WHERE id = %s", (usuario["id"], (nota or "")[:255], alerta_id))
    registrar_log(usuario["id"], "ACTUALIZACION", "alertas", alerta_id, f"Alerta atendida. {nota}", origen_llamada)


def crear_alerta(tipo: str, mensaje: str, severidad: str = "MEDIA", origen: str = "SISTEMA",
                 carro_id=None, medicamento_id=None, inventario_id=None, evitar_duplicado: bool = True) -> int | None:
    """Uso interno (analítica y agente). No duplica una alerta pendiente del mismo tipo/carro/medicamento."""
    if tipo not in TIPOS:
        raise ErrorNegocio(f"Tipo de alerta inválido: {tipo}")
    if evitar_duplicado:
        sql = ("SELECT id FROM alertas WHERE atendida = 0 AND tipo = %s AND carro_id <=> %s "
               "AND medicamento_id <=> %s")
        params = [tipo, carro_id, medicamento_id]
        if tipo == "RECOMENDACION_AGENTE":  # las recomendaciones se distinguen por su texto
            sql += " AND mensaje = %s"
            params.append(mensaje[:255])
        existe = consultar(sql, tuple(params), uno=True)
        if existe:
            return None
    return ejecutar(
        "INSERT INTO alertas (inventario_id, carro_id, medicamento_id, tipo, severidad, mensaje, origen) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s)",
        (inventario_id, carro_id, medicamento_id, tipo, severidad, mensaje[:255], origen))


def resumen_alertas() -> dict:
    filas = consultar("SELECT tipo, severidad, COUNT(*) AS n FROM alertas WHERE atendida = 0 GROUP BY tipo, severidad")
    return {"total": sum(f["n"] for f in filas), "detalle": filas}
