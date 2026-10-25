"""Pruebas unitarias: no requieren base de datos."""
from datetime import date, timedelta

import pytest

from src.agente.herramientas import Herramienta
from src.agente.proveedores import ProveedorReglas
from src.bigdata.procesamiento import clave_medicamento
from src.ocr.extractor_fechas import extraer_fecha_texto, extraer_lote
from src.seguridad.contrasenas import hash_password, validar_politica, verificar_password
from src.seguridad.permisos import MATRIZ, PERMISOS, ROLES, PermisoDenegado, exigir_permiso, tiene_permiso
from src.servicios.inventario import calcular_estado


# ---------------- OCR ----------------
@pytest.mark.parametrize("texto,esperado", [
    ("LOT: B8942 EXP: 11/2027 ADRENALINA", "2027-11-01"),
    ("VENC 12/05/2027", "2027-05-12"),              # defecto v1: se leía como 2005-12-01
    ("EXP 2028-03-15", "2028-03-15"),
    ("FV: NOV 2027", "2027-11-01"),
    ("F.V. 03/28", "2028-03-01"),
    ("FAB 01/2024 EXP 01/2027", "2027-01-01"),      # prioriza la fecha de vencimiento
    ("sin fecha", None),
    ("", None),
])
def test_extraer_fecha(texto, esperado):
    assert extraer_fecha_texto(texto) == esperado


def test_extraer_lote():
    assert extraer_lote("LOT: B8942 EXP 11/2027") == "B8942"
    assert extraer_lote("sin datos") is None


# ---------------- Permisos ----------------
def test_matriz_solo_usa_roles_y_permisos_definidos():
    assert set(MATRIZ) == set(ROLES)
    for permisos in MATRIZ.values():
        assert permisos <= set(PERMISOS)


def test_admin_tiene_todo_y_auditor_es_solo_lectura():
    assert MATRIZ["ADMIN"] == set(PERMISOS)
    escritura = {"inventario.registrar", "inventario.editar", "inventario.consumo", "inventario.baja",
                 "alertas.gestionar", "catalogo.gestionar", "usuarios.gestionar"}
    assert not (MATRIZ["AUDITOR"] & escritura)


def test_medico_no_puede_dar_de_baja():
    assert tiene_permiso({"rol": "MEDICO", "activo": 1}, "inventario.consumo")
    assert not tiene_permiso({"rol": "MEDICO", "activo": 1}, "inventario.baja")


def test_usuario_inactivo_no_tiene_permisos():
    assert not tiene_permiso({"rol": "ADMIN", "activo": 0}, "inventario.ver")


def test_exigir_permiso_lanza(monkeypatch):
    import src.database.auditoria as aud
    monkeypatch.setattr(aud, "registrar_evento_seguridad", lambda *a, **k: None)
    with pytest.raises(PermisoDenegado):
        exigir_permiso({"rol": "OFICIAL_SEGURIDAD", "activo": 1}, "inventario.registrar")


# ---------------- Contraseñas ----------------
def test_bcrypt_y_politica():
    h = hash_password("Carro#Paro2026")
    assert h.startswith("$2")
    assert verificar_password("Carro#Paro2026", h) == (True, False)
    assert verificar_password("otra", h)[0] is False
    assert validar_politica("Carro#Paro2026") == []
    assert len(validar_politica("123456")) >= 3


def test_migracion_sha256_y_rechazo_texto_plano():
    sha = "8d969eef6ecad3c29a3a629280e686cf0c3f5d5a86aff3ca12020c923adc6c92"   # '123456' en la v1
    assert verificar_password("123456", sha) == (True, True)   # válida y debe re-hashearse
    assert verificar_password("hash_demo_123", "hash_demo_123")[0] is False   # la v1 aceptaba esto


# ---------------- Reglas de negocio ----------------
def test_calcular_estado():
    hoy = date(2026, 9, 19)
    assert calcular_estado(hoy - timedelta(days=1), 3, hoy) == "vencido"
    assert calcular_estado(hoy + timedelta(days=10), 3, hoy) == "proximo_a_vencer"
    assert calcular_estado(hoy + timedelta(days=200), 3, hoy) == "vigente"
    assert calcular_estado(hoy + timedelta(days=200), 0, hoy) == "agotado"


def test_normalizacion_nombres_big_data():
    assert clave_medicamento("  ADRENALINA 1 mg/ml ") == clave_medicamento("Adrenalina 1mg/ml")
    assert clave_medicamento("Lidocaína 2%") == "lidocaina2%"


# ---------------- Agente (sin BD) ----------------
def _h(nombre, props=None):
    return Herramienta(nombre, "", "x", lambda u: None, {"type": "object", "properties": props or {}})


def test_agente_reglas_enruta_y_extrae_carro():
    p = ProveedorReglas()
    herramientas = [_h("consultar_vencimientos", {"carro": {}, "dias": {}}), _h("resumen_inventario")]
    paso = p.siguiente_paso("¿Qué vence en CP-URG-01?", [], herramientas)
    assert paso.llamadas == [("consultar_vencimientos", {"carro": "CP-URG-01"})]


def test_agente_informa_herramientas_no_permitidas():
    p = ProveedorReglas()
    paso = p.siguiente_paso("hay riesgo de desabastecimiento", [], [_h("resumen_inventario")])
    assert paso.llamadas[0][0] == "resumen_inventario"
    assert "predecir_desabastecimiento" in p.denegadas


# ---------------- Visitante, login y MFA ----------------
def test_login_rechaza_caracteres_distintos():
    from src.seguridad.correos import login_valido
    for bueno in ("admin", "ana.perez@hospital.co", "user_1+x-y"):
        assert login_valido(bueno)
    for malo in ("admin'--", "a b", "x;drop", "<script>", "ñandú", "a\"b", "", "a" * 300):
        assert not login_valido(malo)


def test_visitante_solo_ve_modulos_asignados():
    from src.seguridad.permisos import permisos_de_usuario, vista_permitida
    sin = {"rol": "VISITANTE", "modulos": ""}
    assert permisos_de_usuario(sin) == set()
    solo_tablero = {"rol": "VISITANTE", "modulos": "tablero"}
    assert vista_permitida(solo_tablero, "tablero")
    assert not vista_permitida(solo_tablero, "usuarios")
    assert not vista_permitida(solo_tablero, "inventario")
    assert not any(p.endswith((".editar", ".crear", ".eliminar")) for p in permisos_de_usuario(solo_tablero))


def test_visitante_modulo_inventado_sin_permisos():
    from src.seguridad.permisos import permisos_de_usuario
    assert permisos_de_usuario({"rol": "VISITANTE", "modulos": "admin,nan"}) == set()


def test_mfa_obligatorio_para_roles_administrativos():
    from src.seguridad.mfa import mfa_obligatorio
    for rol in ("ADMIN", "TI", "OFICIAL_SEGURIDAD", "DIRECCION_MEDICA", "REGENTE_FARMACIA"):
        assert mfa_obligatorio(rol)
    assert not mfa_obligatorio("VISITANTE")
