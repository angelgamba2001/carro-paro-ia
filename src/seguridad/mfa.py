"""
Segundo factor de autenticación (MFA) con TOTP — códigos de 6 dígitos que cambian
cada 30 segundos, compatibles con Microsoft Authenticator, Google Authenticator, etc.

El secreto se guarda en la BD CIFRADO (Fernet, ver cifrado.py) y el código se calcula en el dispositivo del usuario;
no viaja nada por la red. Además:
  * un código no se puede reutilizar (se guarda el último intervalo usado),
  * se aceptan códigos de respaldo de un solo uso (guardados con bcrypt),
  * los roles con permisos críticos están obligados a activarlo.
"""
import base64
import io
import secrets
import time

import pyotp

from src import config

from src.database.connection import consultar, ejecutar
from src.seguridad.cifrado import cifrar, descifrar
from src.seguridad.contrasenas import hash_password, verificar_password

EMISOR = "SMARTDATA 360 Carro de Paro"
VENTANA = config.MFA_VENTANA    # 1 = tolera ±30 s de desfase de reloj; 0 = solo el código actual
TOTAL_RESPALDO = 8

# Roles que pueden modificar catálogo, dar de baja lotes, gestionar cuentas o hacer que el
# agente actúe (DIRECCION_MEDICA puede registrar recomendaciones: agente.acciones)
ROLES_MFA_OBLIGATORIO = {"ADMIN", "REGENTE_FARMACIA", "TI", "OFICIAL_SEGURIDAD", "DIRECCION_MEDICA"}


# Un rol creado desde la interfaz que incluya cualquiera de estos permisos también
# obliga al segundo factor: crear un rol nuevo no puede ser la vía para evitarlo.
PERMISOS_CRITICOS = {"usuarios.gestionar", "usuarios.desbloquear", "catalogo.gestionar", "inventario.baja",
                     "agente.acciones", "bigdata.ejecutar", "seguridad.ver", "auditoria.ver"}


def pendiente_vencido(desde, ahora=None) -> bool:
    """¿Lleva demasiado esperando la pantalla del código? Pasado MFA_PENDIENTE_MINUTOS hay que volver
    a empezar: un código sin usar no debe quedar abierto indefinidamente en una pantalla olvidada."""
    from datetime import datetime, timedelta
    return bool(desde) and (ahora or datetime.now()) - desde > timedelta(minutes=config.MFA_PENDIENTE_MINUTOS)


def mfa_obligatorio(rol: str, extras=()) -> bool:
    """¿Debe tener segundo factor? Cuenta el rol principal y los adicionales."""
    from src.seguridad.permisos import ROLES_BASE, permisos_de
    for r in (rol, *(extras or ())):
        if r in ROLES_MFA_OBLIGATORIO:
            return True
        if r not in ROLES_BASE and permisos_de(r) & PERMISOS_CRITICOS:
            return True
    return False


def estado_mfa(usuario_id: int) -> dict:
    u = consultar("SELECT rol, mfa_activo, mfa_confirmado FROM usuarios WHERE id = %s",
                  (usuario_id,), uno=True) or {}
    activo = bool(u.get("mfa_activo")) and bool(u.get("mfa_confirmado"))
    from src.seguridad.permisos import roles_adicionales
    obligatorio = mfa_obligatorio(u.get("rol", ""), roles_adicionales(usuario_id))
    return {"activo": activo, "obligatorio": obligatorio, "pendiente": obligatorio and not activo}


# ---------------------------------------------------------------------------
# Activación
# ---------------------------------------------------------------------------
def iniciar_activacion(usuario_id: int, correo: str) -> tuple[str, str]:
    """Genera un secreto nuevo (aún sin confirmar) y devuelve (secreto, uri para el QR)."""
    secreto = pyotp.random_base32()
    ejecutar("UPDATE usuarios SET totp_secret = %s, mfa_activo = 0, mfa_confirmado = 0 WHERE id = %s",
             (cifrar(secreto), usuario_id))
    uri = pyotp.TOTP(secreto).provisioning_uri(name=correo, issuer_name=EMISOR)
    return secreto, uri


def qr_png(uri: str) -> bytes:
    """Imagen PNG del código QR para escanear con la app del celular."""
    import qrcode
    imagen = qrcode.make(uri)
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    return buffer.getvalue()


def confirmar_activacion(usuario_id: int, codigo: str) -> list[str]:
    """Verifica el primer código y activa el MFA. Devuelve los códigos de respaldo."""
    u = consultar("SELECT correo, totp_secret FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u or not u["totp_secret"]:
        raise ValueError("Primero genere el código QR.")
    if not pyotp.TOTP(descifrar(u["totp_secret"])).verify(_limpiar(codigo), valid_window=VENTANA):
        raise ValueError("El código no es correcto. Verifique la hora de su celular e intente de nuevo.")
    ejecutar("UPDATE usuarios SET mfa_activo = 1, mfa_confirmado = 1 WHERE id = %s", (usuario_id,))
    from src.database.auditoria import registrar_evento_seguridad
    registrar_evento_seguridad("MFA_ACTIVADO", u["correo"], usuario_id)
    return _generar_codigos_respaldo(usuario_id)


def desactivar(usuario_id: int, codigo: str):
    """Solo se puede desactivar demostrando que se tiene el segundo factor."""
    u = consultar("SELECT correo, rol FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    from src.seguridad.permisos import roles_adicionales
    if mfa_obligatorio(u["rol"], roles_adicionales(usuario_id)):
        raise ValueError(f"El rol {u['rol']} no puede desactivar la verificación en dos pasos.")
    if not verificar_segundo_factor(usuario_id, codigo):
        raise ValueError("El código no es correcto.")
    ejecutar("UPDATE usuarios SET totp_secret = NULL, mfa_activo = 0, mfa_confirmado = 0 WHERE id = %s",
             (usuario_id,))
    ejecutar("DELETE FROM codigos_respaldo WHERE usuario_id = %s", (usuario_id,))
    from src.database.auditoria import registrar_evento_seguridad
    registrar_evento_seguridad("MFA_DESACTIVADO", u["correo"], usuario_id)


# ---------------------------------------------------------------------------
# Verificación
# ---------------------------------------------------------------------------
def _limpiar(codigo: str) -> str:
    return "".join((codigo or "").split()).replace("-", "").upper()


def verificar_segundo_factor(usuario_id: int, codigo: str) -> bool:
    """Acepta un código TOTP vigente (no reutilizado) o un código de respaldo sin usar."""
    codigo = _limpiar(codigo)
    if not codigo:
        return False
    u = consultar("SELECT totp_secret, totp_ultimo_intervalo FROM usuarios WHERE id = %s",
                  (usuario_id,), uno=True)
    if not u or not u["totp_secret"]:
        return False
    if codigo.isdigit() and len(codigo) == 6:
        totp = pyotp.TOTP(descifrar(u["totp_secret"]))
        intervalo = int(time.time()) // 30
        for desfase in range(-VENTANA, VENTANA + 1):
            actual = intervalo + desfase
            if totp.at(actual * 30) == codigo:
                if u["totp_ultimo_intervalo"] and actual <= u["totp_ultimo_intervalo"]:
                    return False       # código ya usado: evita reutilizarlo en los 30 s siguientes
                ejecutar("UPDATE usuarios SET totp_ultimo_intervalo = %s WHERE id = %s", (actual, usuario_id))
                return True
        return False
    return _consumir_codigo_respaldo(usuario_id, codigo)


# ---------------------------------------------------------------------------
# Códigos de respaldo
# ---------------------------------------------------------------------------
def _generar_codigos_respaldo(usuario_id: int) -> list[str]:
    ejecutar("DELETE FROM codigos_respaldo WHERE usuario_id = %s", (usuario_id,))
    codigos = []
    for _ in range(TOTAL_RESPALDO):
        crudo = base64.b32encode(secrets.token_bytes(5)).decode().rstrip("=")[:8]
        codigos.append(crudo)
        ejecutar("INSERT INTO codigos_respaldo (usuario_id, codigo_hash) VALUES (%s, %s)",
                 (usuario_id, hash_password(crudo)))
    return codigos


def regenerar_codigos_respaldo(usuario_id: int, codigo: str) -> list[str]:
    if not verificar_segundo_factor(usuario_id, codigo):
        raise ValueError("El código no es correcto.")
    return _generar_codigos_respaldo(usuario_id)


def _consumir_codigo_respaldo(usuario_id: int, codigo: str) -> bool:
    filas = consultar("SELECT id, codigo_hash FROM codigos_respaldo WHERE usuario_id = %s AND usado = 0",
                      (usuario_id,))
    for f in filas:
        if verificar_password(codigo, f["codigo_hash"])[0]:
            ejecutar("UPDATE codigos_respaldo SET usado = 1, fecha_uso = NOW() WHERE id = %s", (f["id"],))
            from src.database.auditoria import registrar_evento_seguridad
            registrar_evento_seguridad("MFA_CODIGO_RESPALDO", usuario_id=usuario_id,
                                       detalle=f"Quedan {len(filas) - 1} códigos")
            return True
    return False


def codigos_respaldo_restantes(usuario_id: int) -> int:
    r = consultar("SELECT COUNT(*) AS n FROM codigos_respaldo WHERE usuario_id = %s AND usado = 0",
                  (usuario_id,), uno=True)
    return int(r["n"]) if r else 0
