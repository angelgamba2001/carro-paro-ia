"""
Separa dos problemas que dan el mismo error 1045:
  (a) el .env está mal escrito y la contraseña llega con comillas o espacios;
  (b) la contraseña simplemente no es la de su MySQL.

    python probar_clave.py

Primero muestra exactamente qué cadena está leyendo del .env —con los caracteres
invisibles a la vista— y luego le deja probar contraseñas a mano, sin tocar el
archivo, hasta dar con la correcta.
"""
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mysql.connector  # noqa: E402

from src import config  # noqa: E402


def intentar(usuario: str, clave: str) -> bool:
    """Conecta SIN base de datos: así se prueba solo el usuario y la clave."""
    try:
        c = mysql.connector.connect(host=config.DB_HOST, port=config.DB_PORT,
                                    user=usuario, password=clave, connection_timeout=6)
    except mysql.connector.Error as e:
        print(f"   -> rechazada ({e.errno}: {e.msg})")
        return False
    cur = c.cursor()
    cur.execute("SHOW DATABASES")
    bases = [b[0] for b in cur.fetchall()]
    cur.close(); c.close()
    print("   -> CORRECTA")
    print(f"   Bases visibles: {', '.join(bases)}")
    print(f"   ¿Está carro_paro_db? {'sí' if 'carro_paro_db' in bases else 'no, hay que crearla'}")
    return True


def main():
    leida = config.DB_PASSWORD
    print("Lo que el .env le entrega a la aplicación, carácter por carácter:\n")
    print(f"   DB_USER     -> {config.DB_USER!r}")
    print(f"   DB_PASSWORD -> {leida!r}")
    print(f"   longitud    -> {len(leida)} caracteres\n")

    avisos = []
    if leida != leida.strip():
        avisos.append("Empieza o termina con espacios. Bórrelos en el .env.")
    if len(leida) > 1 and leida[0] == leida[-1] and leida[0] in "\"'":
        avisos.append("Está entre comillas. En un .env la contraseña va sin comillas.")
    if "#" in leida:
        avisos.append("Contiene '#'. Si era un comentario del .env, quedó pegado al valor.")
    if leida.lower().startswith("cambie-esto"):
        avisos.append("Sigue el texto de ejemplo del .env.example, sin reemplazar.")
    if avisos:
        print("Problemas en cómo está escrita la línea del .env:")
        for a in avisos:
            print(f"   - {a}")
        print()

    print(f"Probando la contraseña del .env con el usuario '{config.DB_USER}':")
    if intentar(config.DB_USER, leida):
        print("\nEntonces el problema no es la contraseña. Ejecute de nuevo:")
        print("   python diagnostico_mysql.py")
        return 0

    print("\nAhora pruébela a mano. No se guarda ni se muestra en pantalla.")
    print("Escriba la contraseña de su MySQL y pulse Enter (Enter vacío para salir).\n")
    for intento in range(1, 6):
        clave = getpass.getpass(f"Contraseña de '{config.DB_USER}' [{intento}/5]: ")
        if not clave:
            break
        if intentar(config.DB_USER, clave):
            print("\nEsa es la buena. Ábra el .env y deje la línea así, sin comillas:\n")
            print(f"   DB_PASSWORD={clave}\n")
            print("Guarde, y luego:  python diagnostico_mysql.py")
            return 0

    print("\nNinguna funcionó. Dos salidas:")
    print("  1. Abra MySQL Workbench: la conexión que ya usa ahí tiene el usuario y la")
    print("     contraseña buenos. En Workbench, botón derecho sobre la conexión ->")
    print("     Edit Connection, y mire el campo Username.")
    print("  2. Si olvidó la contraseña de root, es más rápido crear un usuario nuevo.")
    print("     En Workbench abra una pestaña de consulta y ejecute:\n")
    print("        CREATE USER 'carro'@'localhost' IDENTIFIED BY 'Carro#2026';")
    print("        GRANT ALL PRIVILEGES ON *.* TO 'carro'@'localhost' WITH GRANT OPTION;")
    print("        FLUSH PRIVILEGES;\n")
    print("     Y en el .env ponga:  DB_USER=carro   y   DB_PASSWORD=Carro#2026")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
