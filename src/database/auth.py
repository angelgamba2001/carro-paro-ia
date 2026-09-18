import hashlib
from src.database.connection import obtener_conexion

def hash_password(password: str) -> str:
    """Genera un hash SHA-256 sencillo para la contraseña."""
    return hashlib.sha256(password.encode()).hexdigest()

def verificar_credenciales(correo: str, password_plana: str):
    """
    Verifica si el usuario existe y si su contraseña coincide.
    Retorna los datos del usuario o None.
    """
    conn = obtener_conexion()
    if conn:
        cursor = conn.cursor(dictionary=True)
        # Para compatibilidad con contraseñas hash o de prueba inicial
        query = "SELECT id, nombre, correo, rol, activo, password_hash FROM usuarios WHERE correo = %s AND activo = 1;"
        cursor.execute(query, (correo,))
        usuario = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if usuario:
            # Comprobar hash o permitir contraseñas base de prueba
            pass_hash_ingresada = hash_password(password_plana)
            if usuario['password_hash'] == pass_hash_ingresada or usuario['password_hash'] == password_plana:
                return usuario
    return None