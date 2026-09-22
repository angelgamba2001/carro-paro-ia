"""
Servicio de inventario del carro de paro.
Toda operación valida permisos aquí (no en la vista), por lo que la interfaz web,
la API REST y el agente IA comparten exactamente las mismas reglas.
"""
from datetime import date, datetime

import pandas as pd

from src import config
from src.database.auditoria import registrar_log
from src.database.connection import conexion, consultar, consultar_df
from src.seguridad.permisos import exigir_permiso
from src.servicios.errores import ErrorNegocio


def calcular_estado(fecha_vencimiento: date, cantidad: int = 1, hoy: date | None = None) -> str:
    hoy = hoy or date.today()
    if cantidad <= 0:
        return "agotado"
    dias = (fecha_vencimiento - hoy).days
    if dias < 0:
        return "vencido"
    if dias <= config.DIAS_PROXIMO_VENCER:
        return "proximo_a_vencer"
    return "vigente"


_SQL_INVENTARIO = """
    SELECT i.id, c.codigo AS carro, s.nombre AS servicio, i.carro_id, i.medicamento_id,
           m.nombre AS medicamento, m.criticidad, i.lote, i.cantidad, i.fecha_vencimiento,
           DATEDIFF(i.fecha_vencimiento, CURDATE()) AS dias_para_vencer, i.estado,
           i.origen_registro, u.nombre AS registrado_por, i.fecha_registro
    FROM inventario_carro i
    JOIN carros c ON c.id = i.carro_id
    JOIN servicios s ON s.id = c.servicio_id
    JOIN cat_medicamentos m ON m.id = i.medicamento_id
    JOIN usuarios u ON u.id = i.usuario_id
"""


def listar_inventario(usuario: dict, carro_id=None, servicio=None, estados=None,
                      medicamento_id=None, incluir_inactivos=False) -> pd.DataFrame:
    exigir_permiso(usuario, "inventario.ver")
    condiciones, params = [], []
    if not incluir_inactivos:
        condiciones.append("i.estado NOT IN ('agotado','dado_de_baja')")
    if carro_id:
        condiciones.append("i.carro_id = %s"); params.append(carro_id)
    if servicio:
        condiciones.append("s.nombre = %s"); params.append(servicio)
    if medicamento_id:
        condiciones.append("i.medicamento_id = %s"); params.append(medicamento_id)
    if estados:
        condiciones.append("i.estado IN (" + ",".join(["%s"] * len(estados)) + ")"); params.extend(estados)
    sql = _SQL_INVENTARIO + (" WHERE " + " AND ".join(condiciones) if condiciones else "")
    sql += " ORDER BY i.fecha_vencimiento ASC"
    return consultar_df(sql, tuple(params))


def stock_por_carro(usuario: dict) -> pd.DataFrame:
    """Stock vigente de cada medicamento en cada carro frente a su mínimo."""
    exigir_permiso(usuario, "inventario.ver")
    return consultar_df("""
        SELECT c.id AS carro_id, c.codigo AS carro, s.nombre AS servicio,
               m.id AS medicamento_id, m.nombre AS medicamento, m.criticidad,
               m.stock_minimo, m.stock_maximo, m.costo_unitario,
               COALESCE(SUM(CASE WHEN i.estado IN ('vigente','proximo_a_vencer') THEN i.cantidad END), 0) AS stock
        FROM carros c
        JOIN servicios s ON s.id = c.servicio_id
        CROSS JOIN cat_medicamentos m
        LEFT JOIN inventario_carro i ON i.carro_id = c.id AND i.medicamento_id = m.id
        WHERE c.activo = 1 AND m.activo = 1
        GROUP BY c.id, c.codigo, s.nombre, m.id, m.nombre, m.criticidad,
                 m.stock_minimo, m.stock_maximo, m.costo_unitario
        ORDER BY c.codigo, m.nombre
    """).astype({"stock": int, "stock_minimo": int, "stock_maximo": int})


def registrar_lote(usuario: dict, carro_id: int, medicamento_id: int, lote: str, cantidad: int,
                   fecha_vencimiento: date, origen: str = "MANUAL", confianza_ocr: float | None = None,
                   origen_llamada: str = "WEB") -> int:
    exigir_permiso(usuario, "inventario.registrar", origen_llamada)
    lote = (lote or "").strip().upper()
    if not lote or len(lote) > 60:
        raise ErrorNegocio("El lote es obligatorio (máximo 60 caracteres).")
    if not 1 <= int(cantidad) <= 500:
        raise ErrorNegocio("La cantidad debe estar entre 1 y 500.")
    if fecha_vencimiento <= date.today():
        raise ErrorNegocio("No se puede ingresar un lote ya vencido al carro.")
    if origen not in ("MANUAL", "OCR"):
        raise ErrorNegocio("Origen de registro inválido.")

    estado = calcular_estado(fecha_vencimiento, cantidad)
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO inventario_carro (carro_id, medicamento_id, usuario_id, lote, cantidad, "
            "fecha_vencimiento, estado, origen_registro, confianza_ocr, editado_manual) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (carro_id, medicamento_id, usuario["id"], lote, cantidad, fecha_vencimiento, estado,
             origen, confianza_ocr, 1 if origen == "MANUAL" else 0),
        )
        inv_id = cur.lastrowid
        cur.execute(
            "INSERT INTO movimientos (inventario_id, carro_id, medicamento_id, usuario_id, tipo, cantidad, motivo) "
            "VALUES (%s,%s,%s,%s,'INGRESO',%s,%s)",
            (inv_id, carro_id, medicamento_id, usuario["id"], cantidad, f"Ingreso lote {lote}"),
        )
        if estado == "proximo_a_vencer":
            cur.execute(
                "INSERT INTO alertas (inventario_id, carro_id, medicamento_id, tipo, severidad, mensaje) "
                "VALUES (%s,%s,%s,'PROXIMO_VENCER','MEDIA',%s)",
                (inv_id, carro_id, medicamento_id, f"Lote {lote} ingresó con menos de "
                                                   f"{config.DIAS_PROXIMO_VENCER} días de vida útil"),
            )
        cur.close()
    registrar_log(usuario["id"], "INSERCION", "inventario_carro", inv_id,
                  f"Lote {lote} x{cantidad} ({origen})", origen_llamada)
    return inv_id


def _obtener_lote(inv_id: int) -> dict:
    fila = consultar("SELECT * FROM inventario_carro WHERE id = %s", (inv_id,), uno=True)
    if not fila:
        raise ErrorNegocio(f"No existe el registro de inventario {inv_id}.")
    return fila


def actualizar_lote(usuario: dict, inv_id: int, nuevo_lote: str, origen_llamada: str = "WEB"):
    """Solo se corrige el código de lote. La fecha de vencimiento es inmutable (regla de la v1)."""
    exigir_permiso(usuario, "inventario.editar", origen_llamada)
    nuevo_lote = (nuevo_lote or "").strip().upper()
    if not nuevo_lote:
        raise ErrorNegocio("Indique el nuevo lote.")
    anterior = _obtener_lote(inv_id)
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE inventario_carro SET lote = %s, editado_manual = 1 WHERE id = %s", (nuevo_lote, inv_id))
        cur.close()
    registrar_log(usuario["id"], "ACTUALIZACION", "inventario_carro", inv_id,
                  f"Lote {anterior['lote']} -> {nuevo_lote}", origen_llamada)


def registrar_consumo(usuario: dict, inv_id: int, cantidad: int, motivo: str = "",
                      codigo_azul: bool = False, origen_llamada: str = "WEB"):
    exigir_permiso(usuario, "inventario.consumo", origen_llamada)
    lote = _obtener_lote(inv_id)
    if lote["estado"] in ("vencido", "agotado", "dado_de_baja"):
        raise ErrorNegocio(f"El lote está en estado '{lote['estado']}' y no puede consumirse.")
    if not 1 <= int(cantidad) <= lote["cantidad"]:
        raise ErrorNegocio(f"Cantidad inválida: hay {lote['cantidad']} unidades en el lote.")
    restante = lote["cantidad"] - int(cantidad)
    estado = calcular_estado(lote["fecha_vencimiento"], restante)
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE inventario_carro SET cantidad = %s, estado = %s WHERE id = %s",
                    (restante, estado, inv_id))
        cur.execute(
            "INSERT INTO movimientos (inventario_id, carro_id, medicamento_id, usuario_id, tipo, cantidad, "
            "motivo, evento_codigo_azul) VALUES (%s,%s,%s,%s,'CONSUMO',%s,%s,%s)",
            (inv_id, lote["carro_id"], lote["medicamento_id"], usuario["id"], cantidad,
             (motivo or "")[:255], 1 if codigo_azul else 0),
        )
        cur.close()
    registrar_log(usuario["id"], "CONSUMO", "inventario_carro", inv_id,
                  f"Consumo de {cantidad} ud. Código azul: {'sí' if codigo_azul else 'no'}", origen_llamada)
    generar_alertas_stock()


def dar_de_baja(usuario: dict, inv_id: int, motivo: str, origen_llamada: str = "WEB"):
    """Reemplaza el DELETE físico de la v1: el registro se conserva para trazabilidad."""
    exigir_permiso(usuario, "inventario.baja", origen_llamada)
    if not (motivo or "").strip():
        raise ErrorNegocio("Indique el motivo de la baja.")
    lote = _obtener_lote(inv_id)
    if lote["estado"] == "dado_de_baja":
        raise ErrorNegocio("El lote ya fue dado de baja.")
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE inventario_carro SET estado = 'dado_de_baja' WHERE id = %s", (inv_id,))
        if lote["cantidad"] > 0:
            cur.execute(
                "INSERT INTO movimientos (inventario_id, carro_id, medicamento_id, usuario_id, tipo, cantidad, motivo) "
                "VALUES (%s,%s,%s,%s,'BAJA_VENCIMIENTO',%s,%s)",
                (inv_id, lote["carro_id"], lote["medicamento_id"], usuario["id"], lote["cantidad"], motivo[:255]),
            )
        cur.execute("UPDATE alertas SET atendida = 1, atendida_por = %s, fecha_atencion = NOW(), "
                    "nota_atencion = 'Lote dado de baja' WHERE inventario_id = %s AND atendida = 0",
                    (usuario["id"], inv_id))
        cur.close()
    registrar_log(usuario["id"], "BAJA", "inventario_carro", inv_id, motivo, origen_llamada)
    generar_alertas_stock()


# ---------------------------------------------------------------------------
# Procesos automáticos (no dependen del usuario; los invoca la app o el pipeline)
# ---------------------------------------------------------------------------
def recalcular_estados() -> dict:
    """Corrige el defecto de la v1: el estado solo se calculaba al registrar y nunca
    cambiaba con el paso de los días. Además genera las alertas de vencimiento que falten."""
    dias = config.DIAS_PROXIMO_VENCER
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute("""UPDATE inventario_carro SET estado = 'vencido'
                       WHERE estado IN ('vigente','proximo_a_vencer') AND fecha_vencimiento < CURDATE()""")
        vencidos = cur.rowcount
        cur.execute("""UPDATE inventario_carro SET estado = 'proximo_a_vencer'
                       WHERE estado = 'vigente' AND fecha_vencimiento <= DATE_ADD(CURDATE(), INTERVAL %s DAY)""",
                    (dias,))
        proximos = cur.rowcount
        for tipo, estado, severidad in (("VENCIDO", "vencido", "ALTA"), ("PROXIMO_VENCER", "proximo_a_vencer", "MEDIA")):
            cur.execute(f"""
                INSERT INTO alertas (inventario_id, carro_id, medicamento_id, tipo, severidad, mensaje)
                SELECT i.id, i.carro_id, i.medicamento_id, '{tipo}', '{severidad}',
                       CONCAT('Lote ', i.lote, ' vence el ', DATE_FORMAT(i.fecha_vencimiento, '%Y-%m-%d'))
                FROM inventario_carro i
                WHERE i.estado = '{estado}' AND i.cantidad > 0
                  AND NOT EXISTS (SELECT 1 FROM alertas a WHERE a.inventario_id = i.id AND a.tipo = '{tipo}')
            """)
        cur.close()
    stock = generar_alertas_stock()
    return {"vencidos": vencidos, "proximos": proximos, "alertas_stock": stock}


def generar_alertas_stock() -> int:
    """Alerta STOCK_BAJO por (carro, medicamento) bajo el mínimo, sin duplicar pendientes."""
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO alertas (carro_id, medicamento_id, tipo, severidad, mensaje)
            SELECT x.carro_id, x.medicamento_id, 'STOCK_BAJO',
                   IF(x.criticidad = 'ALTA', 'ALTA', 'MEDIA'),
                   CONCAT(x.medicamento, ' en ', x.codigo, ': ', x.stock, ' de ', x.stock_minimo, ' mínimas')
            FROM (
                SELECT c.id AS carro_id, c.codigo, m.id AS medicamento_id, m.nombre AS medicamento,
                       m.criticidad, m.stock_minimo,
                       COALESCE(SUM(CASE WHEN i.estado IN ('vigente','proximo_a_vencer') THEN i.cantidad END), 0) AS stock
                FROM carros c CROSS JOIN cat_medicamentos m
                LEFT JOIN inventario_carro i ON i.carro_id = c.id AND i.medicamento_id = m.id
                WHERE c.activo = 1 AND m.activo = 1
                GROUP BY c.id, c.codigo, m.id, m.nombre, m.criticidad, m.stock_minimo
            ) x
            WHERE x.stock < x.stock_minimo
              AND NOT EXISTS (SELECT 1 FROM alertas a WHERE a.carro_id = x.carro_id
                              AND a.medicamento_id = x.medicamento_id AND a.tipo = 'STOCK_BAJO' AND a.atendida = 0)
        """)
        n = cur.rowcount
        cur.close()
    return n


def listar_carros() -> list[dict]:
    return consultar("""SELECT c.id, c.codigo, s.nombre AS servicio, c.ubicacion
                        FROM carros c JOIN servicios s ON s.id = c.servicio_id
                        WHERE c.activo = 1 ORDER BY c.codigo""")


def listar_servicios() -> list[str]:
    return [f["nombre"] for f in consultar("SELECT nombre FROM servicios ORDER BY nombre")]


def listar_movimientos(usuario: dict, dias: int = 90) -> pd.DataFrame:
    exigir_permiso(usuario, "inventario.ver")
    return consultar_df("""
        SELECT mv.fecha, mv.tipo, c.codigo AS carro, m.nombre AS medicamento, mv.cantidad,
               mv.evento_codigo_azul, mv.motivo, u.nombre AS usuario
        FROM movimientos mv
        JOIN carros c ON c.id = mv.carro_id
        JOIN cat_medicamentos m ON m.id = mv.medicamento_id
        JOIN usuarios u ON u.id = mv.usuario_id
        WHERE mv.fecha >= DATE_SUB(NOW(), INTERVAL %s DAY)
        ORDER BY mv.fecha DESC
    """, (dias,))
