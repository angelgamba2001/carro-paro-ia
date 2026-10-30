"""
Completa la base de datos con lo que necesitan los controles de seguridad ampliados.
No borra ni modifica datos existentes (salvo cifrar los secretos TOTP que estén en claro).

    python scripts/migrar_seguridad.py

  * usuario_rol        roles adicionales de una persona (un usuario puede tener varios)
  * sesiones_activas   sesiones web vigentes: permite cerrar la sesión en el servidor
  * errores_sistema    errores de la aplicación y de la API, consultables desde la interfaz
  * cambios_correo     cambio de correo pendiente de confirmar con un código
  * usuarios.totp_secret ampliada a 255 y cifrada (Fernet)

Es idempotente: se puede ejecutar varias veces.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                              # noqa: E402
from src.database.connection import conexion, consultar, ejecutar   # noqa: E402
from src.seguridad.cifrado import cifrar, esta_cifrado               # noqa: E402

TABLAS = {
    "usuario_permiso": """
        CREATE TABLE IF NOT EXISTS usuario_permiso (
            usuario_id INT NOT NULL,
            permiso    VARCHAR(60) NOT NULL,
            fecha      DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (usuario_id, permiso),
            CONSTRAINT fk_permiso_individual_usuario FOREIGN KEY (usuario_id)
                REFERENCES usuarios(id) ON DELETE CASCADE
        ) ENGINE=InnoDB""",
    "configuracion": """
        CREATE TABLE IF NOT EXISTS configuracion (
            clave       VARCHAR(60) PRIMARY KEY,
            valor       VARCHAR(255) NOT NULL,
            usuario_id  INT NULL,
            actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB""",
    "usuario_rol": """
        CREATE TABLE IF NOT EXISTS usuario_rol (
            usuario_id INT NOT NULL,
            rol        VARCHAR(30) NOT NULL,
            fecha      DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (usuario_id, rol),
            CONSTRAINT fk_ur_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            CONSTRAINT fk_ur_rol     FOREIGN KEY (rol)        REFERENCES roles(codigo) ON DELETE CASCADE
        ) ENGINE=InnoDB""",
    "sesiones_activas": """
        CREATE TABLE IF NOT EXISTS sesiones_activas (
            token      CHAR(32) PRIMARY KEY,
            usuario_id INT NOT NULL,
            origen     VARCHAR(20) NOT NULL DEFAULT 'WEB',
            creada     DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_sesion_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
            INDEX idx_sesion_usuario (usuario_id)
        ) ENGINE=InnoDB""",
    "errores_sistema": """
        CREATE TABLE IF NOT EXISTS errores_sistema (
            id       BIGINT AUTO_INCREMENT PRIMARY KEY,
            fecha    DATETIME DEFAULT CURRENT_TIMESTAMP,
            nivel    VARCHAR(10) NOT NULL,
            modulo   VARCHAR(80) NOT NULL,
            mensaje  VARCHAR(500) NOT NULL,
            traza    TEXT NULL,
            INDEX idx_err_fecha (fecha)
        ) ENGINE=InnoDB""",
    "cambios_correo": """
        CREATE TABLE IF NOT EXISTS cambios_correo (
            usuario_id   INT PRIMARY KEY,
            correo_nuevo VARCHAR(150) NOT NULL,
            codigo_hash  VARCHAR(255) NOT NULL,
            vence        DATETIME NOT NULL,
            intentos     INT NOT NULL DEFAULT 0,
            creado       DATETIME DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT fk_cc_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        ) ENGINE=InnoDB""",
}


def main():
    print(f"Base de datos: {config.DB_NAME}\n")
    with conexion() as conn:
        cur = conn.cursor()
        for nombre, ddl in TABLAS.items():
            cur.execute(ddl)
            print(f"✔ tabla {nombre} lista")
        cur.close()

    col = consultar("SELECT CHARACTER_MAXIMUM_LENGTH AS n FROM information_schema.columns "
                    "WHERE table_schema = DATABASE() AND table_name = 'usuarios' "
                    "AND column_name = 'totp_secret'", uno=True)
    if col and (col["n"] or 0) < 255:
        ejecutar("ALTER TABLE usuarios MODIFY totp_secret VARCHAR(255) NULL")
        print("✔ usuarios.totp_secret ampliada a 255")

    pendientes = [f for f in consultar("SELECT id, totp_secret FROM usuarios WHERE totp_secret IS NOT NULL")
                  if not esta_cifrado(f["totp_secret"])]
    for f in pendientes:
        ejecutar("UPDATE usuarios SET totp_secret = %s WHERE id = %s", (cifrar(f["totp_secret"]), f["id"]))
    print(f"✔ secretos TOTP cifrados: {len(pendientes)}")
    print("\nListo.")


if __name__ == "__main__":
    main()
