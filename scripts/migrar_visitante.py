"""
Añade a `usuarios` la columna `modulos`, donde se guarda qué módulos puede abrir una
cuenta con rol VISITANTE (claves separadas por coma, p. ej. "tablero,alertas").
No toca los datos existentes y se puede ejecutar varias veces.

    python scripts/migrar_visitante.py

Sin esta columna el sistema sigue funcionando (el ingreso no se rompe), pero no se
pueden crear visitantes con módulos asignados.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                    # noqa: E402
from src.database.connection import consultar, ejecutar   # noqa: E402


def existe(tabla: str, columna: str) -> bool:
    return bool(consultar(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = %s "
        "AND table_name = %s AND column_name = %s",
        (config.DB_NAME, tabla, columna), uno=True))


def main():
    print(f"Base de datos: {config.DB_NAME}\n")
    if existe("usuarios", "modulos"):
        print("  = modulos                ya existía")
        print("\nNada que hacer: ya estaba al día.")
    else:
        ejecutar("ALTER TABLE usuarios ADD COLUMN modulos VARCHAR(255) NULL")
        print("  + modulos                módulos que puede abrir una cuenta VISITANTE")
        print("\n1 cambio(s) aplicado(s).")
    print("Nada de lo existente se modificó.")


if __name__ == "__main__":
    main()
