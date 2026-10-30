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


# ---------------- Controles de seguridad ampliados (casos 5, 8, 15-20) ----------------
def _png_valido() -> bytes:
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def sin_bd(monkeypatch):
    """Evita escribir eventos en la base de datos y anota los que se habrían escrito."""
    eventos = []
    monkeypatch.setattr("src.seguridad.archivos.registrar_evento_seguridad",
                        lambda tipo, *a, **k: eventos.append((tipo, a, k)))
    return eventos


def test_cifrado_secreto_totp_ida_y_vuelta():
    from src.seguridad.cifrado import cifrar, descifrar, esta_cifrado
    secreto = "JBSWY3DPEHPK3PXP"
    c = cifrar(secreto)
    assert esta_cifrado(c) and secreto not in c
    assert descifrar(c) == secreto
    assert cifrar(c) == c                         # no se cifra dos veces
    assert descifrar(secreto) == secreto          # un secreto antiguo, en claro, se sigue leyendo
    assert cifrar(None) is None and descifrar("") == ""


def test_cifrado_detecta_clave_distinta(monkeypatch):
    from src import config
    from src.seguridad.cifrado import cifrar, descifrar
    c = cifrar("ABC234")
    monkeypatch.setattr(config, "CLAVE_CIFRADO", "")
    monkeypatch.setattr(config, "JWT_SECRETO", "otro-secreto")
    with pytest.raises(ValueError):
        descifrar(c)


def test_imagen_valida_pasa(sin_bd):
    from src.seguridad.archivos import validar_imagen
    assert validar_imagen(_png_valido(), "etiqueta.png") == "png"
    assert not sin_bd


@pytest.mark.parametrize("contenido,nombre", [
    (b"MZ\x90\x00" + b"\x00" * 200, "virus.png"),                 # .exe renombrado a imagen
    (b"%PDF-1.7 ...", "documento.png"),                            # PDF con extensión de imagen
    (b"", "vacio.png"),
    (b"\x89PNG\r\n\x1a\n" + b"basura", "rota.png"),                # firma de PNG, contenido dañado
    (b"texto cualquiera", "nota.jpg"),
])
def test_archivo_falso_se_rechaza(contenido, nombre, sin_bd):
    from src.seguridad.archivos import ArchivoInvalido, validar_imagen
    with pytest.raises(ArchivoInvalido):
        validar_imagen(contenido, nombre, {"id": 1, "correo": "a@b.co"})
    assert sin_bd and sin_bd[-1][0] == "ARCHIVO_RECHAZADO"


def test_extension_debe_coincidir_con_el_contenido(sin_bd):
    from src.seguridad.archivos import ArchivoInvalido, validar_imagen
    with pytest.raises(ArchivoInvalido):
        validar_imagen(_png_valido(), "foto.jpg")                  # PNG disfrazado de JPG


def test_imagen_demasiado_grande(sin_bd):
    from src.seguridad.archivos import MAX_BYTES, ArchivoInvalido, validar_imagen
    with pytest.raises(ArchivoInvalido):
        validar_imagen(_png_valido() + b"0" * MAX_BYTES, "grande.png")


@pytest.fixture
def roles_bd(monkeypatch):
    """Simula roles creados desde la interfaz sin tocar la base de datos."""
    import time

    from src.seguridad import permisos as p
    roles = {"R_LECTOR_ALERTAS": ("Lector de alertas", "x"), "R_BAJAS": ("Bajas", "x")}
    permisos = {"R_LECTOR_ALERTAS": {"alertas.ver", "dashboard.operativo"},
                "R_BAJAS": {"inventario.baja", "inventario.ver"}}
    monkeypatch.setitem(p._cache, "roles", roles)
    monkeypatch.setitem(p._cache, "permisos", permisos)
    monkeypatch.setitem(p._cache, "t", time.monotonic() + 3600)
    return roles


def test_rol_personalizado_tiene_sus_permisos(roles_bd):
    from src.seguridad.permisos import ROLES, permisos_de_usuario, tiene_permiso
    u = {"id": 1, "rol": "R_LECTOR_ALERTAS", "activo": 1}
    assert "R_LECTOR_ALERTAS" in ROLES and ROLES["R_LECTOR_ALERTAS"][0] == "Lector de alertas"
    assert permisos_de_usuario(u) == {"alertas.ver", "dashboard.operativo"}
    assert tiene_permiso(u, "alertas.ver") and not tiene_permiso(u, "usuarios.gestionar")


def test_dos_roles_suman_permisos(roles_bd):
    from src.seguridad.permisos import permisos_de_usuario
    u = {"id": 1, "rol": "R_LECTOR_ALERTAS", "activo": 1, "roles_extra": ["R_BAJAS", "AUDITOR"]}
    efectivos = permisos_de_usuario(u)
    assert {"alertas.ver", "inventario.baja", "auditoria.ver"} <= efectivos
    sin_extras = permisos_de_usuario({**u, "roles_extra": []})
    assert "inventario.baja" not in sin_extras           # quitar el rol quita sus permisos


def test_visitante_ignora_roles_adicionales(roles_bd):
    from src.seguridad.permisos import permisos_de_usuario
    u = {"id": 1, "rol": "VISITANTE", "activo": 1, "modulos": "alertas", "roles_extra": ["ADMIN"]}
    assert permisos_de_usuario(u) == {"alertas.ver"}


def test_rol_adicional_visitante_no_concede(roles_bd):
    from src.seguridad.permisos import permisos_de_usuario
    u = {"id": 1, "rol": "AUDITOR", "activo": 1, "roles_extra": ["VISITANTE"]}
    assert permisos_de_usuario(u) == permisos_de_usuario({**u, "roles_extra": []})


def test_permiso_inventado_en_rol_no_concede(monkeypatch):
    import time

    from src.seguridad import permisos as p
    monkeypatch.setitem(p._cache, "roles", {"R_X": ("X", "x")})
    monkeypatch.setitem(p._cache, "permisos", {"R_X": {"alertas.ver"}})
    monkeypatch.setitem(p._cache, "t", time.monotonic() + 3600)
    assert p.permisos_de("R_X") == {"alertas.ver"}
    assert p.permisos_de("R_NO_EXISTE") == set()


def test_mfa_obligatorio_en_rol_personalizado_con_permiso_critico(roles_bd):
    from src.seguridad.mfa import mfa_obligatorio
    assert mfa_obligatorio("R_BAJAS")                       # incluye inventario.baja
    assert not mfa_obligatorio("R_LECTOR_ALERTAS")
    assert mfa_obligatorio("R_LECTOR_ALERTAS", ["ADMIN"])    # un rol adicional crítico también obliga


def test_nadie_concede_permisos_que_no_tiene():
    from src.servicios.errores import ErrorNegocio
    from src.servicios.roles import _codigo, _exigir_alcance, _validar_permisos
    jefe = {"id": 1, "rol": "REGENTE_FARMACIA", "activo": 1}
    _exigir_alcance(jefe, {"inventario.baja"})
    with pytest.raises(ErrorNegocio):
        _exigir_alcance(jefe, {"usuarios.gestionar"})
    with pytest.raises(ErrorNegocio):
        _validar_permisos([])
    with pytest.raises(ErrorNegocio):
        _validar_permisos(["permiso.inventado"])
    assert _codigo("Lector de Alertas Ñandú") == "R_LECTOR_DE_ALERTAS_NANDU"
    assert _codigo("x" * 80).startswith("R_") and len(_codigo("x" * 80)) <= 30


def test_sesion_sin_tabla_no_bloquea_el_ingreso(monkeypatch):
    from src.seguridad import sesiones
    monkeypatch.setattr(sesiones, "disponible", lambda: False)
    assert sesiones.crear({"id": 1}) == ""
    assert sesiones.vigente("", 1) is True
    assert sesiones.vigente("token-cualquiera", 1) is True


def test_registro_de_errores_va_a_la_tabla_sin_bucle(monkeypatch):
    import logging
    import sys

    from src import registro_errores
    guardados = []
    monkeypatch.setattr("src.database.connection.ejecutar", lambda sql, params=(): guardados.append(params))
    h = registro_errores._TablaErrores(level=logging.ERROR)
    try:
        raise RuntimeError("fallo forzado")
    except RuntimeError:
        rec = logging.LogRecord("app", logging.ERROR, __file__, 1, "Error en la vista %s", ("tablero",),
                                sys.exc_info())
    h.emit(rec)
    assert guardados and guardados[0][0] == "ERROR" and "tablero" in guardados[0][2]
    assert "RuntimeError" in guardados[0][3]

    def falla(*a, **k):
        raise ConnectionError("sin base de datos")
    monkeypatch.setattr("src.database.connection.ejecutar", falla)
    h.emit(rec)                                            # no debe lanzar ni recursar


def test_login_rechaza_quince_caracteres_especiales():
    from src.seguridad.correos import login_valido
    assert not login_valido("!#$%&/()=?¡¿*{}[]")
    assert not login_valido("' OR '1'='1")


def test_secuencia_numerica_no_cumple_la_politica():
    from src.seguridad.contrasenas import validar_politica
    assert validar_politica("123456789101112131415")
    assert validar_politica("a")                           # un solo carácter
    assert not validar_politica("Carro#Paro2026")


def test_pendiente_mfa_vence():
    from datetime import datetime, timedelta

    from src import config
    from src.seguridad.mfa import pendiente_vencido
    ahora = datetime.now()
    assert not pendiente_vencido(ahora - timedelta(minutes=config.MFA_PENDIENTE_MINUTOS - 1), ahora)
    assert pendiente_vencido(ahora - timedelta(minutes=config.MFA_PENDIENTE_MINUTOS + 1), ahora)
    assert not pendiente_vencido(None, ahora)


def test_mirilla_de_contrasena_oculta():
    from app.componentes import OCULTAR_MIRILLA
    assert "display:none" in OCULTAR_MIRILLA and "assword" in OCULTAR_MIRILLA


# --- Correcciones de la lista de 20 pruebas de seguridad -------------------------------

def test_permisos_individuales_se_suman_al_rol():
    from src.seguridad.permisos import permisos_de_usuario
    base = permisos_de_usuario({"rol": "ENFERMERO", "activo": 1})
    con = permisos_de_usuario({"rol": "ENFERMERO", "activo": 1,
                               "permisos_extra": ["usuarios.gestionar", "permiso.inventado"]})
    assert "usuarios.gestionar" not in base
    assert "usuarios.gestionar" in con
    assert "permiso.inventado" not in con          # una clave alterada nunca concede nada


def test_ajustes_de_expiracion_respetan_el_rango(monkeypatch):
    from src.seguridad import ajustes
    monkeypatch.setattr(ajustes, "_leer", lambda: {"MINUTOS_INACTIVIDAD": "5", "JWT_MINUTOS_EXPIRACION": "99999"})
    assert ajustes.minutos_inactividad() == 5
    assert ajustes.minutos_jwt() == ajustes.por_defecto("JWT_MINUTOS_EXPIRACION")   # fuera de rango -> .env
    monkeypatch.setattr(ajustes, "_leer", lambda: {})
    assert ajustes.minutos_inactividad() == ajustes.por_defecto("MINUTOS_INACTIVIDAD")


def test_pantalla_de_acceso_oculta_la_mirilla():
    from app.estilos import BASE
    assert "stTextInputRevealButton" in BASE and "display: none" in BASE


def test_eliminar_usuario_exige_permiso():
    import pytest

    from src.seguridad.permisos import PermisoDenegado
    from src.servicios import usuarios as srv
    enfermero = {"id": 2, "rol": "ENFERMERO", "correo": "e@x.co", "nombre": "E", "roles_extra": []}
    with pytest.raises(PermisoDenegado):
        srv.eliminar_usuario(enfermero, 3, "z@x.co")


def test_permisos_quitados_restan_a_rol_y_extras():
    from src.seguridad.permisos import permisos_de, permisos_de_usuario
    base = permisos_de("ENFERMERO")
    quitar = sorted(base)[0]
    u = {"rol": "ENFERMERO", "activo": 1, "permisos_quitados": [quitar, "no.existe"],
         "permisos_extra": [quitar]}
    efectivos = permisos_de_usuario(u)
    assert quitar not in efectivos                      # lo quitado gana, incluso sobre un permiso individual
    assert efectivos == base - {quitar}


def test_quitar_permisos_exige_permiso():
    import pytest

    from src.seguridad.permisos import PermisoDenegado
    from src.servicios import roles as srv
    enfermero = {"id": 2, "rol": "ENFERMERO", "correo": "e@x.co", "nombre": "E", "roles_extra": []}
    with pytest.raises(PermisoDenegado):
        srv.cambiar_permisos_quitados(enfermero, 3, ["inventario.baja"])
