import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture(scope="session")
def bd():
    """Pruebas de integración: se omiten si no hay MySQL con el esquema inicializado.

    Antes de empezar se devuelve el estado de autenticación de todas las cuentas a
    su punto de partida. Sin esto, basta con que alguien active la verificación en
    dos pasos usando la aplicación —o que una prueba anterior se interrumpa a la
    mitad— para que la suite falle por motivos que no tienen nada que ver con el
    cambio que se está probando. Los datos del negocio no se tocan.
    """
    from src.database.connection import base_disponible
    if not base_disponible():
        pytest.skip("MySQL no disponible (ejecute scripts/inicializar_bd.py)")

    from src.database.connection import consultar, ejecutar

    def hay(columna: str) -> bool:
        return bool(consultar(
            "SELECT 1 FROM information_schema.columns WHERE table_schema = DATABASE() "
            "AND table_name = 'usuarios' AND column_name = %s", (columna,), uno=True))

    campos = ["intentos_fallidos = 0", "bloqueado_hasta = NULL",
              "totp_secret = NULL", "mfa_activo = 0", "mfa_confirmado = 0"]
    if hay("totp_ultimo_intervalo"):
        campos.append("totp_ultimo_intervalo = NULL")
    if hay("mfa_correo_activo"):                      # migrar_correo.py ya aplicado
        campos += ["mfa_correo_activo = 0", "mfa_correo_hash = NULL",
                   "mfa_correo_vence = NULL", "mfa_correo_intentos = 0",
                   "mfa_correo_enviado = NULL"]
    if hay("ms_oid"):
        campos.append("ms_oid = NULL")
    ejecutar("UPDATE usuarios SET " + ", ".join(campos))
    ejecutar("DELETE FROM codigos_respaldo")
    return True


@pytest.fixture(autouse=True)
def correo_desactivado(monkeypatch):
    """Ninguna prueba debe escribir archivos de correo ni intentar salir a la red."""
    monkeypatch.setattr("src.config.CORREO_MODO", "desactivado", raising=False)
