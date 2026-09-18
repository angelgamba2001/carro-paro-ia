from src.database.connection import obtener_conexion

def registrar_log(usuario_id: int, accion: str, entidad: str, entidad_id: int = None, detalle: str = None):
    """
    Inserta un evento en la tabla log_auditoria.
    Acciones válidas: INSERCION, ACTUALIZACION, ELIMINACION, LECTURA_OCR, CONSULTA_AGENTE
    """
    conn = obtener_conexion()
    if conn:
        try:
            cursor = conn.cursor()
            query = """
                INSERT INTO log_auditoria (usuario_id, accion, entidad, entidad_id, detalle)
                VALUES (%s, %s, %s, %s, %s);
            """
            cursor.execute(query, (usuario_id, accion, entidad, entidad_id, detalle))
            conn.commit()
            cursor.close()
        except Exception as e:
            print(f"Error al registrar log de auditoria: {e}")
        finally:
            conn.close()