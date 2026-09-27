"""
Prepara la base de datos para el registro de usuarios por cuenta propia.

    python scripts/migrar_registro.py

Añade el estado de la cuenta y los campos de verificación del correo. Las cuentas
que ya existen quedan como ACTIVO, así que nadie pierde el acceso.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                    # noqa: E402
from src.database.connection import consultar, ejecutar   # noqa: E402

COLUMNAS = [
    ("estado", "VARCHAR(24) NOT NULL DEFAULT 'ACTIVO'",
     "PENDIENTE_CORREO, PENDIENTE_APROBACION, ACTIVO o RECHAZADO"),
    ("correo_verificado", "TINYINT NOT NULL DEFAULT 1",
     "si la persona demostró que el buzón es suyo"),
    ("verificacion_hash", "VARCHAR(255) NULL",
     "código de verificación vigente, con bcrypt"),
    ("verificacion_vence", "DATETIME NULL",
     "hasta cuándo sirve ese código"),
    ("verificacion_intentos", "INT NOT NULL DEFAULT 0",
     "intentos fallidos contra el código actual"),
    ("verificacion_enviado", "DATETIME NULL",
     "último envío, para no permitir pedir códigos en cadena"),
    ("aprobado_por", "INT NULL",
     "quién autorizó la cuenta y le asignó el rol"),
    ("aprobado_en", "DATETIME NULL",
     "cuándo se autorizó"),
    ("motivo_rechazo", "VARCHAR(255) NULL",
     "por qué se rechazó una solicitud"),
]


def existe(columna: str) -> bool:
    return bool(consultar(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = %s "
        "AND table_name = 'usuarios' AND column_name = %s",
        (config.DB_NAME, columna), uno=True))


def main():
    print(f"Base de datos: {config.DB_NAME}\n")
    nuevas = 0
    for nombre, definicion, para_que in COLUMNAS:
        if existe(nombre):
            print(f"  = {nombre:24} ya existía")
            continue
        ejecutar(f"ALTER TABLE usuarios ADD COLUMN {nombre} {definicion}")
        print(f"  + {nombre:24} {para_que}")
        nuevas += 1

    if not consultar("SELECT 1 FROM information_schema.statistics WHERE table_schema = %s "
                     "AND table_name = 'usuarios' AND index_name = 'idx_usuarios_estado'",
                     (config.DB_NAME,), uno=True):
        ejecutar("CREATE INDEX idx_usuarios_estado ON usuarios (estado)")
        print("  + índice idx_usuarios_estado")
        nuevas += 1

    # Perfil de espera. La columna `rol` tiene clave foránea a `roles`, así que quien
    # se registra necesita un rol real; este no tiene ningún permiso asociado, de modo
    # que la cuenta existe y no puede hacer absolutamente nada hasta que la autoricen.
    if not consultar("SELECT 1 FROM roles WHERE codigo = 'SIN_ASIGNAR'", uno=True):
        ejecutar("INSERT INTO roles (codigo, nombre, descripcion) VALUES (%s,%s,%s)",
                 ("SIN_ASIGNAR", "Sin perfil asignado",
                  "Cuenta registrada cuyo acceso todavía no ha sido autorizado. "
                  "No tiene ningún permiso."))
        print("  + rol SIN_ASIGNAR (sin permisos)")
        nuevas += 1

    # Las cuentas creadas por un administrador ya estaban autorizadas
    ejecutar("UPDATE usuarios SET estado = 'ACTIVO', correo_verificado = 1 "
             "WHERE activo = 1 AND estado = 'ACTIVO'")

    print(f"\n{nuevas} cambio(s) aplicado(s)." if nuevas else "\nNada que hacer: ya estaba al día.")
    print("Las cuentas existentes quedaron como ACTIVO; nadie pierde el acceso.")


if __name__ == "__main__":
    main()
