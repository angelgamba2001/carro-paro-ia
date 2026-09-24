"""
Agrega el segundo factor (MFA/TOTP) a una base de datos que ya existe, sin borrar datos.

    python scripts/migrar_mfa.py

Es idempotente: se puede ejecutar varias veces sin problema.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import conexion, consultar  # noqa: E402

COLUMNAS = {
    "totp_secret": "VARCHAR(64) NULL",
    "mfa_activo": "TINYINT NOT NULL DEFAULT 0",
    "mfa_confirmado": "TINYINT NOT NULL DEFAULT 0",
    "totp_ultimo_intervalo": "BIGINT NULL",
}

TABLA_RESPALDO = """
CREATE TABLE IF NOT EXISTS codigos_respaldo (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id   INT NOT NULL,
    codigo_hash  VARCHAR(255) NOT NULL,
    usado        TINYINT NOT NULL DEFAULT 0,
    fecha_uso    DATETIME NULL,
    fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_respaldo_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    INDEX idx_respaldo_usuario (usuario_id, usado)
) ENGINE=InnoDB
"""


def main():
    existentes = {f["COLUMN_NAME"] for f in consultar(
        "SELECT COLUMN_NAME FROM information_schema.columns "
        "WHERE table_schema = DATABASE() AND table_name = 'usuarios'")}
    with conexion() as conn:
        cur = conn.cursor()
        for nombre, definicion in COLUMNAS.items():
            if nombre not in existentes:
                cur.execute(f"ALTER TABLE usuarios ADD COLUMN {nombre} {definicion}")
                print(f"✔ columna usuarios.{nombre} agregada")
            else:
                print(f"– usuarios.{nombre} ya existía")
        cur.execute(TABLA_RESPALDO)
        cur.close()
    print("✔ tabla codigos_respaldo lista")
    print("\nListo. Active la verificación en dos pasos desde 'Mi cuenta' en la aplicación.")


if __name__ == "__main__":
    main()
