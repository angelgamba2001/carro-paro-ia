import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

def obtener_conexion():
    """
    Establece y retorna una conexion activa a la base de datos MySQL.
    """
    try:
        conexion = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", "carro_paro_db"),
            port=int(os.getenv("DB_PORT", 3306))
        )
        if conexion.is_connected():
            return conexion
    except Error as e:
        print(f"Error al conectar a MySQL: {e}")
        return None

if __name__ == "__main__":
    # Prueba rapida de conexion
    conn = obtener_conexion()
    if conn:
        print("¡Conexion exitosa a carro_paro_db!")
        conn.close()