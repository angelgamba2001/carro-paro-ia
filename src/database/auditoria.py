"""Registro de auditoría y de eventos de seguridad. Nunca interrumpe la operación."""
import logging

from src.database.connection import ejecutar

log = logging.getLogger(__name__)


def registrar_log(usuario_id, accion: str, entidad: str, entidad_id=None,
                  detalle: str = None, origen: str = "WEB"):
    """Acciones: INSERCION, ACTUALIZACION, BAJA, CONSUMO, CREACION_USUARIO, LECTURA_OCR,
    CONSULTA_AGENTE, ACCION_AGENTE, EJECUCION_PIPELINE, ..."""
    try:
        ejecutar(
            "INSERT INTO log_auditoria (usuario_id, accion, entidad, entidad_id, detalle, origen) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (usuario_id, accion, entidad, entidad_id, (detalle or "")[:500], origen),
        )
    except Exception as e:  # la auditoría no debe tumbar la operación, pero sí quedar en el log técnico
        log.error("No se pudo registrar auditoría: %s", e)


def registrar_evento_seguridad(tipo: str, correo: str = None, usuario_id=None,
                               detalle: str = None, origen: str = "WEB"):
    try:
        ejecutar(
            "INSERT INTO eventos_seguridad (usuario_id, correo, tipo, origen, detalle) "
            "VALUES (%s, %s, %s, %s, %s)",
            (usuario_id, (correo or "")[:150], tipo, origen, (detalle or "")[:255]),
        )
    except Exception as e:
        log.error("No se pudo registrar evento de seguridad: %s", e)
