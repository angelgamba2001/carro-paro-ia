"""
Por qué no conecta MySQL.

    python diagnostico_mysql.py

verificar_entorno.py solo dice "sin conexión". Este script muestra el error exacto
que devuelve MySQL y qué hacer en cada caso.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mysql.connector  # noqa: E402
from mysql.connector import errorcode  # noqa: E402

from src import config  # noqa: E402

REMEDIOS = {
    errorcode.ER_ACCESS_DENIED_ERROR: (
        "El usuario o la contraseña no son los de su MySQL.",
        ["Abra .env y corrija DB_USER y DB_PASSWORD.",
         "El usuario suele ser 'root' y la contraseña la que puso al instalar MySQL.",
         "Si la contraseña tiene # o espacios, escríbala tal cual, sin comillas."],
    ),
    errorcode.ER_BAD_DB_ERROR: (
        "MySQL responde y las credenciales son correctas, pero la base de datos no existe.",
        ["Ejecute:  python scripts/inicializar_bd.py",
         "Eso crea carro_paro_db con las 17 tablas y los datos de demostración."],
    ),
    2003: (
        "MySQL no está escuchando: el servicio está detenido o usa otro puerto.",
        ["Abra 'Servicios' en Windows (Win+R, escriba services.msc).",
         "Busque MySQL80 y púlselo con el botón derecho -> Iniciar.",
         "Si su MySQL usa otro puerto, ajuste DB_PORT en .env."],
    ),
}


def main():
    print("Valores que está usando la aplicación (leídos de .env):")
    print(f"  DB_HOST     = {config.DB_HOST}")
    print(f"  DB_PORT     = {config.DB_PORT}")
    print(f"  DB_USER     = {config.DB_USER}")
    clave = config.DB_PASSWORD
    print(f"  DB_PASSWORD = {'(vacía)' if not clave else '*' * len(clave) + f'  ({len(clave)} caracteres)'}")
    print(f"  DB_NAME     = {config.DB_NAME}\n")

    try:
        conn = mysql.connector.connect(
            host=config.DB_HOST, port=config.DB_PORT,
            user=config.DB_USER, password=config.DB_PASSWORD,
            database=config.DB_NAME, connection_timeout=6,
        )
    except mysql.connector.Error as e:
        titulo, pasos = REMEDIOS.get(e.errno, ("MySQL rechazó la conexión.", []))
        print(f"MySQL respondió con el error {e.errno}:")
        print(f"  {e.msg}\n")
        print(f"Qué significa: {titulo}")
        for i, p in enumerate(pasos, 1):
            print(f"  {i}. {p}")
        if not pasos:
            print("  Copie el mensaje de arriba para poder buscar la causa concreta.")
        return 1

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = %s",
                (config.DB_NAME,))
    tablas = cur.fetchone()[0]
    cur.close()
    conn.close()

    print(f"Conexión correcta. La base {config.DB_NAME} tiene {tablas} tablas.")
    if tablas < 17:
        print("\nFaltan tablas. Ejecute:  python scripts/inicializar_bd.py")
        return 1
    print("Todo listo:  streamlit run app/main.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
