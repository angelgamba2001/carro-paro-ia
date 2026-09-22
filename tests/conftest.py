import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def bd():
    """Pruebas de integración: se omiten si no hay MySQL con el esquema inicializado."""
    from src.database.connection import base_disponible
    if not base_disponible():
        pytest.skip("MySQL no disponible (ejecute scripts/inicializar_bd.py)")
    return True
