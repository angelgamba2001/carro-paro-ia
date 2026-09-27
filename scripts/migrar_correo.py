"""
Añade a `usuarios` lo que necesitan el segundo factor por correo y el inicio de
sesión con Microsoft. No toca los datos existentes y se puede ejecutar varias
veces: comprueba cada columna antes de crearla.

    python scripts/migrar_correo.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                    # noqa: E402
from src.database.connection import consultar, ejecutar   # noqa: E402

COLUMNAS = [
    # (nombre, definición, para qué sirve)
    ("mfa_correo_activo", "TINYINT NOT NULL DEFAULT 0",
     "el usuario aceptó recibir el código por correo"),
    ("mfa_correo_hash", "VARCHAR(255) NULL",
     "código vigente, guardado con bcrypt"),
    ("mfa_correo_vence", "DATETIME NULL",
     "hasta cuándo sirve ese código"),
    ("mfa_correo_intentos", "INT NOT NULL DEFAULT 0",
     "intentos fallidos contra el código actual"),
    ("mfa_correo_enviado", "DATETIME NULL",
     "último envío, para no permitir pedir códigos en cadena"),
    ("ms_oid", "VARCHAR(64) NULL",
     "identificador de la cuenta en Entra ID (no cambia aunque cambie el correo)"),
    ("ultimo_acceso_origen", "VARCHAR(20) NULL",
     "por dónde entró la última vez: WEB, MICROSOFT o API"),
]


def existe(tabla: str, columna: str) -> bool:
    return bool(consultar(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = %s "
        "AND table_name = %s AND column_name = %s",
        (config.DB_NAME, tabla, columna), uno=True))


def main():
    print(f"Base de datos: {config.DB_NAME}\n")
    nuevas = 0
    for nombre, definicion, para_que in COLUMNAS:
        if existe("usuarios", nombre):
            print(f"  = {nombre:24} ya existía")
            continue
        ejecutar(f"ALTER TABLE usuarios ADD COLUMN {nombre} {definicion}")
        print(f"  + {nombre:24} {para_que}")
        nuevas += 1

    # El índice hace instantánea la búsqueda por identidad de Microsoft al entrar
    if not consultar("SELECT 1 FROM information_schema.statistics WHERE table_schema = %s "
                     "AND table_name = 'usuarios' AND index_name = 'idx_usuarios_ms_oid'",
                     (config.DB_NAME,), uno=True):
        ejecutar("CREATE INDEX idx_usuarios_ms_oid ON usuarios (ms_oid)")
        print("  + índice idx_usuarios_ms_oid")
        nuevas += 1

    print(f"\n{nuevas} cambio(s) aplicado(s)." if nuevas else "\nNada que hacer: ya estaba al día.")
    print("Nada de lo existente se modificó.")


if __name__ == "__main__":
    main()
