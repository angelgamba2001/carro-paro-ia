"""
Crea la tabla de consentimientos sin borrar datos existentes.

    python scripts/migrar_consentimientos.py

Es idempotente: puede ejecutarse varias veces.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.database.connection import conexion  # noqa: E402

TABLA = """
CREATE TABLE IF NOT EXISTS consentimientos (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    usuario_id  INT NOT NULL,
    version     VARCHAR(20) NOT NULL,
    documento   VARCHAR(40) NOT NULL DEFAULT 'politicas',
    origen      VARCHAR(20) NOT NULL DEFAULT 'WEB',
    fecha       DATETIME DEFAULT CURRENT_TIMESTAMP,
    revocado    TINYINT NOT NULL DEFAULT 0,
    fecha_revocacion DATETIME NULL,
    CONSTRAINT fk_consent_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    INDEX idx_consent_usuario (usuario_id, version, revocado)
) ENGINE=InnoDB
"""


def main():
    with conexion() as conn:
        cur = conn.cursor()
        cur.execute(TABLA)
        cur.close()
    print("✔ tabla consentimientos lista")


if __name__ == "__main__":
    main()
