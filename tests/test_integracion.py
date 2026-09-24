"""Pruebas de integración contra MySQL (se omiten si no hay base de datos)."""
from datetime import date, timedelta

import pytest

from src.seguridad.permisos import PermisoDenegado

PW = "Carro#Paro2026"


def _login(correo):
    from src.seguridad.autenticacion import autenticar
    r = autenticar(correo, PW)
    assert r.ok, r.mensaje
    return r.usuario


def test_login_generico_y_bloqueo(bd):
    from src.database.connection import ejecutar
    from src.seguridad.autenticacion import MENSAJE_GENERICO, autenticar
    ejecutar("UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE correo='auditor@hospital.com'")
    assert autenticar("noexiste@hospital.com", "x").mensaje == MENSAJE_GENERICO
    for _ in range(4):
        assert autenticar("auditor@hospital.com", "mala").mensaje == MENSAJE_GENERICO
    r = autenticar("auditor@hospital.com", "mala")
    assert "bloqueada" in r.mensaje
    assert not autenticar("auditor@hospital.com", PW).ok      # sigue bloqueada aun con la clave correcta
    ejecutar("UPDATE usuarios SET intentos_fallidos=0, bloqueado_hasta=NULL WHERE correo='auditor@hospital.com'")


def test_no_se_ingresa_lote_vencido(bd):
    from src.servicios.errores import ErrorNegocio
    from src.servicios.inventario import registrar_lote
    with pytest.raises(ErrorNegocio):
        registrar_lote(_login("enfermero@hospital.com"), 1, 1, "PRUEBA", 1, date.today() - timedelta(days=1))


def test_auditor_no_registra(bd):
    from src.servicios.inventario import registrar_lote
    with pytest.raises(PermisoDenegado):
        registrar_lote(_login("auditor@hospital.com"), 1, 1, "PRUEBA", 1, date.today() + timedelta(days=90))


def test_consumo_descuenta_y_deja_movimiento(bd):
    from src.database.connection import consultar
    from src.servicios.inventario import registrar_consumo, registrar_lote
    u = _login("enfermero@hospital.com")
    inv = registrar_lote(u, 1, 1, "PYTEST-CONS", 5, date.today() + timedelta(days=200))
    registrar_consumo(u, inv, 2, "prueba", True)
    assert consultar("SELECT cantidad FROM inventario_carro WHERE id=%s", (inv,), uno=True)["cantidad"] == 3
    mov = consultar("SELECT tipo, cantidad FROM movimientos WHERE inventario_id=%s ORDER BY id", (inv,))
    assert [(m["tipo"], m["cantidad"]) for m in mov] == [("INGRESO", 5), ("CONSUMO", 2)]


def test_api_jwt_y_permisos(bd):
    from fastapi.testclient import TestClient
    from api.main import app
    c = TestClient(app)
    assert c.get("/api/inventario").status_code == 401
    assert c.get("/api/inventario", headers={"Authorization": "Bearer manipulado"}).status_code == 401
    t = c.post("/api/auth/login", json={"correo": "medico@hospital.com", "password": PW}).json()["access_token"]
    h = {"Authorization": f"Bearer {t}"}
    assert c.get("/api/inventario", headers=h).status_code == 200
    assert c.get("/api/analitica/predicciones", headers=h).status_code == 403
    r = c.get("/api/salud")
    assert r.headers["X-Frame-Options"] == "DENY"


def test_agente_respeta_rol(bd):
    from src.agente.agente import AgenteCarroParo
    ag = AgenteCarroParo()
    r = ag.responder(_login("enfermero@hospital.com"), "resumen general")
    assert "resumen_inventario" in r["herramientas_usadas"]
    with pytest.raises(PermisoDenegado):
        ag.responder(_login("seguridad@hospital.com"), "resumen")


# --------------------------- Segundo factor (MFA/TOTP) ---------------------------
def _activar_mfa(correo: str):
    """Activa MFA en una cuenta de prueba y devuelve (usuario_id, totp, codigos_respaldo)."""
    import pyotp
    from src.database.connection import consultar
    from src.seguridad import mfa
    uid = consultar("SELECT id FROM usuarios WHERE correo = %s", (correo,), uno=True)["id"]
    secreto, _uri = mfa.iniciar_activacion(uid, correo)
    totp = pyotp.TOTP(secreto)
    codigos = mfa.confirmar_activacion(uid, totp.now())
    return uid, totp, codigos


def _desactivar_mfa(uid: int):
    from src.database.connection import ejecutar
    ejecutar("UPDATE usuarios SET totp_secret=NULL, mfa_activo=0, mfa_confirmado=0, "
             "totp_ultimo_intervalo=NULL, intentos_fallidos=0, bloqueado_hasta=NULL WHERE id=%s", (uid,))
    ejecutar("DELETE FROM codigos_respaldo WHERE usuario_id = %s", (uid,))


def test_mfa_login_en_dos_pasos(bd):
    from src.seguridad.autenticacion import autenticar, completar_login_mfa
    uid, totp, codigos = _activar_mfa("direccion@hospital.com")
    try:
        r = autenticar("direccion@hospital.com", PW)
        assert not r.ok and r.requiere_mfa          # la contraseña sola ya no basta
        assert not completar_login_mfa(uid, "000000").ok
        codigo = totp.now()
        assert completar_login_mfa(uid, codigo).ok
        assert not completar_login_mfa(uid, codigo).ok    # no se puede reutilizar
        assert completar_login_mfa(uid, codigos[0]).ok    # código de respaldo
        assert not completar_login_mfa(uid, codigos[0]).ok
    finally:
        _desactivar_mfa(uid)


def test_mfa_obligatorio_para_roles_criticos(bd):
    from src.seguridad.mfa import ROLES_MFA_OBLIGATORIO, estado_mfa
    from src.database.connection import consultar
    assert {"ADMIN", "REGENTE_FARMACIA"} <= ROLES_MFA_OBLIGATORIO
    uid = consultar("SELECT id FROM usuarios WHERE correo='medico@hospital.com'", uno=True)["id"]
    assert estado_mfa(uid)["obligatorio"] is False


def test_api_token_temporal_no_da_acceso(bd):
    from fastapi.testclient import TestClient
    from api.main import app
    uid, totp, _ = _activar_mfa("direccion@hospital.com")
    try:
        c = TestClient(app)
        r = c.post("/api/auth/login", json={"correo": "direccion@hospital.com", "password": PW}).json()
        assert r["mfa_requerido"] and "access_token" not in r
        temporal = {"Authorization": f"Bearer {r['token_temporal']}"}
        assert c.get("/api/inventario", headers=temporal).status_code == 401
        r2 = c.post("/api/auth/mfa", json={"codigo": totp.now()}, headers=temporal)
        assert r2.status_code == 200
        completo = {"Authorization": f"Bearer {r2.json()['access_token']}"}
        assert c.get("/api/inventario", headers=completo).status_code == 200
    finally:
        _desactivar_mfa(uid)
