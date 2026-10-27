"""Pruebas de integración contra MySQL (se omiten si no hay base de datos)."""
from datetime import date, timedelta
from pathlib import Path

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


# --------------------------- Consentimiento y portada ---------------------------
def test_consentimiento_se_registra_una_vez(bd):
    from src.database.connection import consultar, ejecutar
    from src.servicios.consentimiento import (VERSION_POLITICAS, acepto_version_vigente,
                                              registrar_aceptacion)
    uid = consultar("SELECT id FROM usuarios WHERE correo='auditor@hospital.com'", uno=True)["id"]
    ejecutar("DELETE FROM consentimientos WHERE usuario_id = %s", (uid,))
    try:
        assert acepto_version_vigente(uid) is False
        assert registrar_aceptacion(uid) is True
        assert registrar_aceptacion(uid) is False        # no duplica la misma versión
        assert acepto_version_vigente(uid) is True
        fila = consultar("SELECT version, origen FROM consentimientos WHERE usuario_id = %s",
                         (uid,), uno=True)
        assert fila["version"] == VERSION_POLITICAS and fila["origen"] == "WEB"
    finally:
        ejecutar("DELETE FROM consentimientos WHERE usuario_id = %s", (uid,))


APP = str(Path(__file__).resolve().parent.parent / "app" / "main.py")


def test_portada_exige_aceptar_las_politicas(bd):
    from streamlit.testing.v1 import AppTest
    from src.database.connection import consultar, ejecutar
    uid = consultar("SELECT id FROM usuarios WHERE correo='medico@hospital.com'", uno=True)["id"]
    ejecutar("DELETE FROM consentimientos WHERE usuario_id = %s", (uid,))
    ejecutar("UPDATE usuarios SET intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = %s", (uid,))
    at = AppTest.from_file(APP, default_timeout=120).run()
    [b for b in at.button if b.label == "Acceder"][0].click()      # portada -> pantalla de acceso
    at.run()
    at.text_input[0].input("medico@hospital.com")
    at.text_input[1].input(PW)
    [b for b in at.button if b.label == "Ingresar"][0].click()
    at.run()
    assert not at.sidebar.radio                       # sin aceptar no se inicia sesión
    assert any("acept" in w.value.lower() for w in at.warning)
    assert not consultar("SELECT id FROM consentimientos WHERE usuario_id = %s", (uid,))


def test_documentos_legales_se_abren(bd):
    from streamlit.testing.v1 import AppTest
    from app.legal import CUERPOS, DOCUMENTOS, RESPONSABLE
    esperado = {"privacidad": "Ley 1581", "cookies": "cookies", "terminos": "Ley 1273"}
    for clave, etiqueta in DOCUMENTOS.items():
        at = AppTest.from_file(APP, default_timeout=120).run()
        [b for b in at.button if b.label == etiqueta][0].click()
        at.run()
        assert not at.exception
        texto = " ".join(m.value for m in at.markdown)
        assert esperado[clave].lower() in texto.lower()
        # El documento debe estar terminado: sin espacios por completar
        assert "[" not in CUERPOS[clave]
    assert "[" not in RESPONSABLE


# --------------------------- Recuperación de contraseña ---------------------------
def test_recuperacion_exige_segundo_factor(bd):
    from src.database.connection import consultar
    from src.seguridad.recuperacion import puede_restablecer, restablecer
    uid = consultar("SELECT id FROM usuarios WHERE correo='analista@hospital.com'", uno=True)["id"]
    _desactivar_mfa(uid)
    # Sin segundo factor no se puede restablecer, y el mensaje no revela si la cuenta existe
    sin_mfa = puede_restablecer("analista@hospital.com")
    inexistente = puede_restablecer("nadie@hospital.com")
    assert sin_mfa.ok is False and inexistente.ok is False
    assert sin_mfa.mensaje == inexistente.mensaje

    uid, totp, codigos = _activar_mfa("analista@hospital.com")
    try:
        assert puede_restablecer("analista@hospital.com").ok is True
        assert restablecer(uid, "000000", "ClaveNueva#26", "ClaveNueva#26").ok is False
        assert restablecer(uid, totp.now(), "ClaveNueva#26", "Otra#2026xx").ok is False   # no coinciden
        assert restablecer(uid, totp.now(), "corta", "corta").ok is False                 # política
        assert restablecer(uid, codigos[0], "ClaveNueva#26", "ClaveNueva#26").ok is True  # respaldo
        from src.seguridad.autenticacion import autenticar
        r = autenticar("analista@hospital.com", "ClaveNueva#26")
        assert r.requiere_mfa                      # la contraseña nueva funciona
        assert restablecer(uid, codigos[0], "Otra#2026xyz", "Otra#2026xyz").ok is False   # no se reusa
    finally:
        _desactivar_mfa(uid)
        from src.seguridad.contrasenas import hash_password
        from src.database.connection import ejecutar
        ejecutar("UPDATE usuarios SET password_hash = %s WHERE id = %s", (hash_password(PW), uid))


def test_burbuja_respeta_permisos(bd):
    """La burbuja del asistente solo se dibuja para quien puede usarlo.
    AppTest no tipifica los popover, así que se comprueba por el CSS que inyecta."""
    import datetime

    from streamlit.testing.v1 import AppTest

    from src.agente.herramientas import herramientas_permitidas

    def hay_burbuja(correo):
        at = AppTest.from_file(APP, default_timeout=200)
        at.session_state["usuario"] = _login(correo)
        at.session_state["ultima_actividad"] = datetime.datetime.now()
        at.run()
        return any("burbuja_agente" in m.value for m in at.markdown)

    assert hay_burbuja("medico@hospital.com") is True
    assert hay_burbuja("auditor@hospital.com") is False      # el auditor no usa el asistente
    assert len(herramientas_permitidas(_login("medico@hospital.com"))) < \
           len(herramientas_permitidas(_login("admin@hospital.com")))


def test_agente_herramientas_nuevas(bd):
    from src.agente.herramientas import REGISTRO, ejecutar_herramienta
    for nombre in ("detalle_carro", "comparar_servicios", "buscar_medicamento",
                   "orden_reposicion", "historial_consumo", "atender_alerta"):
        assert nombre in REGISTRO
    u = _login("regente@hospital.com")
    d = ejecutar_herramienta(u, "detalle_carro", {"carro": "CP-URG-01"})
    assert d["carro"] == "CP-URG-01" and "unidades_totales" in d
    assert "carros_disponibles" in ejecutar_herramienta(u, "detalle_carro", {"carro": "NO-EXISTE"})
    c = ejecutar_herramienta(u, "comparar_servicios", {})
    assert len(c["comparacion"]) >= 5
    b = ejecutar_herramienta(u, "buscar_medicamento", {"nombre": "adrenalina"})
    assert b["total_unidades"] >= 0 and b["coincidencias"]
    assert "error" in ejecutar_herramienta(u, "buscar_medicamento", {"nombre": "xy"})


def test_pantalla_recuperar_no_choca_con_las_claves_de_los_widgets(bd):
    """La pantalla de recuperación se abre y acepta un correo sin romperse.

    Regresión: el formulario se llamaba igual que la clave de sesión donde se
    guardaba el correo, y Streamlit prohíbe escribir en la clave de un widget
    ya instanciado (StreamlitWidgetAlreadyInstantiatedError)."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(APP, default_timeout=120).run()
    [b for b in at.button if b.label == "Acceder"][0].click()
    at.run()
    [b for b in at.button if b.label == "Olvidé mi contraseña"][0].click()
    at.run()
    assert not at.exception, f"al abrir la pantalla: {at.exception}"

    # Una cuenta sin segundo factor: no debe restablecer, pero tampoco reventar
    at.text_input[0].input("medico@hospital.com")
    [b for b in at.button if b.label == "Continuar"][0].click()
    at.run()
    assert not at.exception, f"al enviar el correo: {at.exception}"

    # Y una con segundo factor obligatorio, que sí avanza al paso del código
    import pyotp
    from src.database.connection import consultar
    from src.seguridad.mfa import confirmar_activacion, iniciar_activacion
    uid = consultar("SELECT id FROM usuarios WHERE correo='seguridad@hospital.com'", uno=True)["id"]
    secreto, _ = iniciar_activacion(uid, "seguridad@hospital.com")
    confirmar_activacion(uid, pyotp.TOTP(secreto).now())

    try:
        at = AppTest.from_file(APP, default_timeout=120).run()
        [b for b in at.button if b.label == "Acceder"][0].click()
        at.run()
        [b for b in at.button if b.label == "Olvidé mi contraseña"][0].click()
        at.run()
        at.text_input[0].input("seguridad@hospital.com")
        [b for b in at.button if b.label == "Continuar"][0].click()
        at.run()
        assert not at.exception, f"al avanzar al paso del código: {at.exception}"
        assert any("Nueva contraseña" in m.value for m in at.markdown)
    finally:
        # Esta cuenta la usan otras pruebas: se devuelve como estaba
        from src.database.connection import ejecutar
        ejecutar("UPDATE usuarios SET totp_secret = NULL, mfa_activo = 0, "
                 "mfa_confirmado = 0 WHERE id = %s", (uid,))
        ejecutar("DELETE FROM codigos_respaldo WHERE usuario_id = %s", (uid,))


# --------------------------- Correo institucional y SSO ---------------------------
def test_dominios_de_correo_se_validan(bd, monkeypatch):
    from src.seguridad import correos
    monkeypatch.setattr("src.config.DOMINIOS_CORREO", "")
    assert correos.validar("  Nelson.Guevara@Unipamplona.EDU.co ") == "nelson.guevara@unipamplona.edu.co"
    for malo in ("", "sin-arroba", "a@b", "x y@z.com", "x@@y.com"):
        with pytest.raises(ValueError):
            correos.validar(malo)

    # Con lista configurada, solo pasan esos dominios
    monkeypatch.setattr("src.config.DOMINIOS_CORREO", "unipamplona.edu.co, husanrafael.co")
    assert correos.validar("a.b@husanrafael.co")
    with pytest.raises(ValueError, match="Solo se admiten"):
        correos.validar("cualquiera@gmail.com")
    assert correos.es_personal("alguien@outlook.com")


def test_segundo_factor_por_correo(bd, monkeypatch):
    """Un solo uso, con vencimiento, límite de intentos y sin dejar el código en claro."""
    import re
    from datetime import datetime, timedelta
    from src import config
    from src.database.connection import consultar, ejecutar
    from src.seguridad import mfa_correo

    tmp = Path(__file__).resolve().parent.parent / "data" / "correo_saliente"
    monkeypatch.setattr("src.config.CORREO_MODO", "archivo")
    uid = consultar("SELECT id FROM usuarios WHERE correo='analista@hospital.com'", uno=True)["id"]
    try:
        mfa_correo.activar(uid)
        assert mfa_correo.disponible(uid)
        antes = set(tmp.glob("*.html")) if tmp.exists() else set()
        ok, _ = mfa_correo.enviar_codigo(uid)
        assert ok
        nuevo = (set(tmp.glob("*.html")) - antes).pop()
        codigo = "".join(re.search(r'text-align:center;">([\d ]+)<', nuevo.read_text("utf-8")).group(1).split())

        # El código nunca se guarda en claro
        guardado = consultar("SELECT mfa_correo_hash FROM usuarios WHERE id=%s", (uid,), uno=True)
        assert codigo not in guardado["mfa_correo_hash"]

        assert not mfa_correo.verificar(uid, "000000")          # incorrecto
        assert mfa_correo.verificar(uid, codigo)                # correcto
        assert not mfa_correo.verificar(uid, codigo)            # ya consumido

        # Vencido
        ejecutar("UPDATE usuarios SET mfa_correo_enviado = NULL WHERE id=%s", (uid,))
        mfa_correo.enviar_codigo(uid)
        ejecutar("UPDATE usuarios SET mfa_correo_vence = %s WHERE id=%s",
                 (datetime.now() - timedelta(minutes=1), uid))
        assert not mfa_correo.verificar(uid, codigo)

        # Agotar intentos anula el código vigente
        ejecutar("UPDATE usuarios SET mfa_correo_enviado = NULL WHERE id=%s", (uid,))
        mfa_correo.enviar_codigo(uid)
        for _ in range(config.MFA_CORREO_MAX_INTENTOS + 1):
            mfa_correo.verificar(uid, "111111")
        assert consultar("SELECT mfa_correo_hash FROM usuarios WHERE id=%s",
                         (uid,), uno=True)["mfa_correo_hash"] is None
        nuevo.unlink(missing_ok=True)
    finally:
        mfa_correo.activar(uid, False)


def test_login_acepta_el_codigo_del_correo(bd, monkeypatch):
    from src.database.connection import consultar
    from src.seguridad import mfa_correo
    from src.seguridad.autenticacion import autenticar, canal_mfa, completar_login_mfa
    monkeypatch.setattr("src.config.CORREO_MODO", "desactivado")
    uid = consultar("SELECT id FROM usuarios WHERE correo='auditor@hospital.com'", uno=True)["id"]
    try:
        mfa_correo.activar(uid)
        assert canal_mfa(uid) == "correo"
        r = autenticar("auditor@hospital.com", PW)
        assert r.requiere_mfa and r.canal_mfa == "correo"      # no entra solo con la contraseña
        assert completar_login_mfa(uid, "123456").ok is False  # código inventado
    finally:
        mfa_correo.activar(uid, False)


def test_sso_microsoft_rechaza_lo_que_debe(bd, monkeypatch):
    from src.seguridad import microsoft
    monkeypatch.setattr("src.config.MS_CLIENT_ID", "")
    assert not microsoft.configurado()

    monkeypatch.setattr("src.config.DOMINIOS_CORREO", "husanrafael.co")
    monkeypatch.setattr("src.config.MS_ROL_POR_DEFECTO", "")
    # Dominio ajeno
    u, aviso = microsoft.resolver_usuario({"oid": "x", "correo": "ajeno@gmail.com", "nombre": "X"})
    assert u is None and "dominio" in aviso.lower()
    # Dominio válido pero sin cuenta dada de alta: no se crea sola
    u, aviso = microsoft.resolver_usuario({"oid": "y", "correo": "nadie@husanrafael.co", "nombre": "Y"})
    assert u is None and "no está dada de alta" in aviso

    # PKCE: el reto es el SHA-256 del verificador, no el verificador
    import base64, hashlib
    p = microsoft.preparar()
    esperado = base64.urlsafe_b64encode(hashlib.sha256(p["verificador"].encode()).digest()).decode().rstrip("=")
    assert p["reto"] == esperado and p["reto"] != p["verificador"]


# --------------------------- Registro por cuenta propia ---------------------------
def _limpiar_registro(correo):
    from src.database.connection import ejecutar
    ejecutar("DELETE FROM consentimientos WHERE usuario_id IN "
             "(SELECT id FROM usuarios WHERE correo = %s)", (correo,))
    ejecutar("DELETE FROM usuarios WHERE correo = %s", (correo,))


def test_registro_completo_y_aprobacion(bd, monkeypatch):
    """Alta propia -> verificación del correo -> espera -> autorización del admin."""
    import re
    from src.database.connection import consultar
    from src.servicios import registro
    monkeypatch.setattr("src.config.CORREO_MODO", "archivo")
    monkeypatch.setattr("src.config.REGISTRO_ABIERTO", True)
    monkeypatch.setattr("src.config.REGISTRO_ROL_INICIAL", "")   # exige aprobación
    monkeypatch.setattr("src.config.DOMINIOS_CORREO", "")
    carpeta = Path(__file__).resolve().parent.parent / "data" / "correo_saliente"
    correo = "prueba.registro@gmail.com"
    _limpiar_registro(correo)
    try:
        antes = set(carpeta.glob("*.html")) if carpeta.exists() else set()
        r = registro.solicitar_cuenta("Prueba Registro", correo, "Carro#Paro2026", "Carro#Paro2026")
        assert r.ok and r.usuario_id

        # Mientras no verifique el correo, la cuenta no sirve para entrar
        u = consultar("SELECT activo, estado, rol FROM usuarios WHERE id=%s", (r.usuario_id,), uno=True)
        assert u["activo"] == 0 and u["estado"] == "PENDIENTE_CORREO"
        from src.seguridad.autenticacion import autenticar
        assert not autenticar(correo, "Carro#Paro2026").ok

        archivo = (set(carpeta.glob("*.html")) - antes).pop()
        codigo = "".join(re.search(r'text-align:center;">([\d ]+)<',
                                   archivo.read_text("utf-8")).group(1).split())
        assert not registro.verificar_correo(r.usuario_id, "000000").ok
        assert registro.verificar_correo(r.usuario_id, codigo).ok

        # Verificado, pero todavía sin permiso para operar
        u = consultar("SELECT activo, estado FROM usuarios WHERE id=%s", (r.usuario_id,), uno=True)
        assert u["estado"] == "PENDIENTE_APROBACION" and u["activo"] == 0
        assert not autenticar(correo, "Carro#Paro2026").ok
        assert r.usuario_id in [p["id"] for p in registro.pendientes()]

        # El administrador le asigna el perfil
        admin = consultar("SELECT id, nombre FROM usuarios WHERE correo='admin@hospital.com'", uno=True)
        assert registro.aprobar(admin, r.usuario_id, "MEDICO").ok
        u = consultar("SELECT activo, estado, rol FROM usuarios WHERE id=%s", (r.usuario_id,), uno=True)
        assert u["activo"] == 1 and u["estado"] == "ACTIVO" and u["rol"] == "MEDICO"
        assert autenticar(correo, "Carro#Paro2026").ok          # ahora sí entra
        archivo.unlink(missing_ok=True)
    finally:
        _limpiar_registro(correo)


def test_registro_no_deja_elegir_el_rol_ni_delata_correos(bd, monkeypatch):
    from src.database.connection import consultar
    from src.servicios import registro
    monkeypatch.setattr("src.config.CORREO_MODO", "desactivado")
    monkeypatch.setattr("src.config.REGISTRO_ABIERTO", True)
    monkeypatch.setattr("src.config.REGISTRO_ROL_INICIAL", "")
    monkeypatch.setattr("src.config.DOMINIOS_CORREO", "")

    # Un correo que ya existe devuelve el MISMO mensaje que uno nuevo
    existente = registro.solicitar_cuenta("Quien Sea", "admin@hospital.com",
                                          "Carro#Paro2026", "Carro#Paro2026")
    assert existente.ok and existente.mensaje == registro.MENSAJE_ENVIADO
    # ...y no toca la cuenta real
    u = consultar("SELECT rol, estado FROM usuarios WHERE correo='admin@hospital.com'", uno=True)
    assert u["rol"] == "ADMIN" and u["estado"] == "ACTIVO"

    correo = "sin.rol@gmail.com"
    _limpiar_registro(correo)
    try:
        r = registro.solicitar_cuenta("Sin Rol", correo, "Carro#Paro2026", "Carro#Paro2026")
        assert consultar("SELECT rol FROM usuarios WHERE id=%s", (r.usuario_id,), uno=True)["rol"] \
            == "SIN_ASIGNAR"
        # Contraseña floja y correo inválido se rechazan
        assert not registro.solicitar_cuenta("X Y", "otro@gmail.com", "123", "123").ok
        assert not registro.solicitar_cuenta("X Y", "no-es-correo", "Carro#Paro2026",
                                             "Carro#Paro2026").ok
    finally:
        _limpiar_registro(correo)


def test_registro_respeta_la_lista_de_dominios(bd, monkeypatch):
    from src.servicios import registro
    monkeypatch.setattr("src.config.CORREO_MODO", "desactivado")
    monkeypatch.setattr("src.config.REGISTRO_ABIERTO", True)
    monkeypatch.setattr("src.config.DOMINIOS_CORREO", "unipamplona.edu.co")
    r = registro.solicitar_cuenta("Alguien Externo", "alguien@gmail.com",
                                  "Carro#Paro2026", "Carro#Paro2026")
    assert not r.ok and "Solo se admiten" in r.mensaje

    monkeypatch.setattr("src.config.REGISTRO_ABIERTO", False)
    r = registro.solicitar_cuenta("Alguien", "a@unipamplona.edu.co",
                                  "Carro#Paro2026", "Carro#Paro2026")
    assert not r.ok and "deshabilitado" in r.mensaje


def test_pantalla_de_solicitudes_se_dibuja(bd, monkeypatch):
    """La cola de autorización aparece en Usuarios y no rompe la pantalla."""
    from streamlit.testing.v1 import AppTest
    from src.database.connection import consultar
    from src.servicios import registro
    monkeypatch.setattr("src.config.CORREO_MODO", "desactivado")
    monkeypatch.setattr("src.config.REGISTRO_ABIERTO", True)
    monkeypatch.setattr("src.config.REGISTRO_ROL_INICIAL", "")
    monkeypatch.setattr("src.config.DOMINIOS_CORREO", "")

    correo = "pendiente.vista@gmail.com"
    _limpiar_registro(correo)
    uid, totp, _ = _activar_mfa("admin@hospital.com")
    try:
        r = registro.solicitar_cuenta("Pendiente Vista", correo, "Carro#Paro2026", "Carro#Paro2026")
        from src.database.connection import ejecutar
        ejecutar("UPDATE usuarios SET estado='PENDIENTE_APROBACION', correo_verificado=1, "
                 "verificacion_hash=NULL WHERE id=%s", (r.usuario_id,))

        at = AppTest.from_file(APP, default_timeout=200).run()
        [b for b in at.button if b.label == "Acceder"][0].click(); at.run()
        at.text_input[0].input("admin@hospital.com")
        at.text_input[1].input(PW)
        [c for c in at.checkbox][0].check()
        [b for b in at.button if b.label == "Ingresar"][0].click(); at.run()
        at.text_input[0].input(totp.now())
        [b for b in at.button if b.label == "Verificar"][0].click(); at.run()

        at.sidebar.radio[0].set_value("Usuarios").run()
        assert not at.exception, f"la pantalla de usuarios falló: {at.exception}"
        texto = " ".join(m.value for m in at.markdown) + " ".join(
            c.value for c in at.caption if isinstance(c.value, str))
        assert "Pendiente Vista" in texto or correo in texto
    finally:
        _desactivar_mfa(uid)
        _limpiar_registro(correo)


# --------------------------- API para la app móvil ---------------------------
def test_api_serializa_nulos_de_pandas(bd):
    """Regresión: GET /api/alertas devolvía 500 con cualquier alerta pendiente.

    Los huecos de pandas (NaN, NaT) no son JSON válido y el serializador abortaba
    con «Out of range float values». Una alerta sin atender tiene fecha_atencion
    vacía, así que el fallo ocurría siempre."""
    from fastapi.testclient import TestClient
    from api.main import app
    c = TestClient(app)
    t = c.post("/api/auth/login",
               json={"correo": "medico@hospital.com", "password": PW}).json()["access_token"]
    cab = {"Authorization": f"Bearer {t}"}
    for ruta in ("/api/alertas?pendientes=true", "/api/inventario", "/api/inventario/stock"):
        r = c.get(ruta, headers=cab)
        assert r.status_code == 200, f"{ruta} devolvió {r.status_code}"
        filas = r.json()
        assert isinstance(filas, list)
        # Ningún NaN disfrazado: los huecos deben llegar como null
        texto = r.text
        assert "NaN" not in texto and "Infinity" not in texto


def test_api_cors_solo_admite_los_origenes_declarados(bd):
    """La app móvil necesita CORS; una web cualquiera no debe obtenerlo."""
    from fastapi.testclient import TestClient
    from api.main import app
    c = TestClient(app)
    permitido = c.options("/api/auth/login", headers={
        "Origin": "https://localhost", "Access-Control-Request-Method": "POST"})
    assert permitido.status_code == 200
    assert permitido.headers.get("access-control-allow-origin") == "https://localhost"

    ajeno = c.options("/api/auth/login", headers={
        "Origin": "https://sitio-cualquiera.com", "Access-Control-Request-Method": "POST"})
    assert ajeno.headers.get("access-control-allow-origin") is None


# ---------------- Controles de seguridad ampliados ----------------
def _limpiar_pruebas():
    from src.database.connection import ejecutar
    ejecutar("DELETE FROM usuarios WHERE correo LIKE 'pytest-seg-%'")
    ejecutar("DELETE FROM roles WHERE codigo LIKE 'R_PYTEST%'")


def test_rol_personalizado_asignado_a_dos_personas_y_multirol(bd):
    import uuid

    from src.seguridad.permisos import invalidar_cache
    from src.servicios import roles as srv_roles
    from src.servicios import usuarios as srv_usr
    admin = _login("admin@hospital.com")
    _limpiar_pruebas()
    try:
        a = srv_roles.crear_rol(admin, "Pytest Lector", "prueba", ["alertas.ver", "inventario.ver"])
        b = srv_roles.crear_rol(admin, "Pytest Bajas", "prueba", ["inventario.baja", "catalogo.gestionar"])
        ids = [srv_usr.crear_usuario(admin, f"Prueba {i}", f"pytest-seg-{uuid.uuid4().hex[:8]}@hospital.com",
                                     PW, a) for i in range(2)]
        for i in ids:                                       # mismo rol para dos personas
            assert srv_roles.permisos_efectivos(i) == {"alertas.ver", "inventario.ver"}
        srv_roles.cambiar_roles_adicionales(admin, ids[0], [b, "AUDITOR"])   # dos roles más
        efectivos = srv_roles.permisos_efectivos(ids[0])
        assert {"alertas.ver", "inventario.baja", "auditoria.ver"} <= efectivos
        assert srv_roles.permisos_efectivos(ids[1]) == {"alertas.ver", "inventario.ver"}
        srv_roles.cambiar_permisos_rol(admin, a, ["alertas.ver"])           # se modifican sus permisos
        invalidar_cache()
        assert srv_roles.permisos_efectivos(ids[1]) == {"alertas.ver"}
        with pytest.raises(Exception):
            srv_roles.eliminar_rol(admin, a)                                # tiene personas asignadas
    finally:
        _limpiar_pruebas()
        invalidar_cache()


def test_correo_duplicado_se_rechaza(bd):
    import uuid

    from src.servicios import usuarios as srv_usr
    from src.servicios.errores import ErrorNegocio
    admin = _login("admin@hospital.com")
    _limpiar_pruebas()
    correo = f"pytest-seg-{uuid.uuid4().hex[:8]}@hospital.com"
    try:
        srv_usr.crear_usuario(admin, "Prueba", correo, PW, "ENFERMERO")
        with pytest.raises(ErrorNegocio):
            srv_usr.crear_usuario(admin, "Prueba 2", correo.upper(), PW, "ENFERMERO")
    finally:
        _limpiar_pruebas()


def test_sesion_unica_cierra_la_anterior(bd):
    from src.seguridad import sesiones
    from src.servicios.errores import ErrorNegocio  # noqa: F401
    u = _login("enfermero@hospital.com")
    if not sesiones.disponible():
        pytest.skip("Falta python scripts/migrar_seguridad.py")
    primera = sesiones.crear(u)
    segunda = sesiones.crear(u)
    assert primera and segunda and primera != segunda
    assert not sesiones.vigente(primera, u["id"])           # la primera quedó cerrada
    assert sesiones.vigente(segunda, u["id"])
    sesiones.cerrar(segunda)
    assert not sesiones.vigente(segunda, u["id"])


def test_totp_se_guarda_cifrado(bd):
    from src.database.connection import consultar
    from src.seguridad import mfa
    u = _login("enfermero@hospital.com")
    secreto, _ = mfa.iniciar_activacion(u["id"], u["correo"])
    guardado = consultar("SELECT totp_secret FROM usuarios WHERE id = %s", (u["id"],), uno=True)["totp_secret"]
    assert guardado.startswith("enc:") and secreto not in guardado
    from src.database.connection import ejecutar
    ejecutar("UPDATE usuarios SET totp_secret = NULL, mfa_activo = 0, mfa_confirmado = 0 WHERE id = %s", (u["id"],))
