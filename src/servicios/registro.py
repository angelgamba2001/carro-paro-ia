"""
Registro de usuarios por cuenta propia, con verificación del correo.

Cómo funciona, de principio a fin:

  1. La persona llena el formulario con su correo real y una contraseña.
  2. Recibe un código de seis dígitos en ese buzón. Hasta que lo escriba, la cuenta
     existe pero no sirve para nada: estado PENDIENTE_CORREO.
  3. Al verificar, pasa a PENDIENTE_APROBACION —esperando que un administrador le
     asigne el rol— o directamente a ACTIVO si REGISTRO_ROL_INICIAL está configurado.
  4. Cuando el administrador aprueba, la persona recibe un correo y ya puede entrar.

Por qué el rol NO lo elige quien se registra: en este sistema el rol decide quién
puede dar de baja medicamentos, modificar el catálogo o gestionar cuentas. Si el
formulario dejara elegirlo, registrarse sería equivalente a autoasignarse permisos.
Quien se registra demuestra que el buzón es suyo; que además deba operar carros de
paro lo decide la institución.

Sobre la enumeración de correos: el mensaje es el mismo exista o no la cuenta. Si ya
existe, en lugar de decirlo se avisa al dueño de que alguien intentó registrarse con
su dirección, que es información útil para él y para nadie más.
"""
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from src import config
from src.database.auditoria import registrar_evento_seguridad, registrar_log
from src.database.connection import consultar, ejecutar
from src.seguridad.contrasenas import hash_password, validar_politica, verificar_password
from src.seguridad.correos import validar as validar_correo
from src.servicios import correo as servicio_correo

log = logging.getLogger(__name__)

LONGITUD_CODIGO = 6
MAX_INTENTOS = 5
SEGUNDOS_ENTRE_ENVIOS = 60

# El mismo texto exista o no la cuenta
MENSAJE_ENVIADO = ("Si esa dirección puede registrarse, le enviamos un código de verificación. "
                   "Revise su correo, incluida la carpeta de no deseado.")

ESTADOS = {
    "PENDIENTE_CORREO": "Falta verificar el correo",
    "PENDIENTE_APROBACION": "Esperando autorización",
    "ACTIVO": "Activa",
    "RECHAZADO": "Rechazada",
}


@dataclass
class Resultado:
    ok: bool
    mensaje: str = ""
    usuario_id: int | None = None
    errores: list | None = None


# ---------------------------------------------------------------------------
# Alta
# ---------------------------------------------------------------------------
def solicitar_cuenta(nombre: str, correo: str, password: str, repetir: str) -> Resultado:
    """Crea la cuenta en estado PENDIENTE_CORREO y manda el código."""
    if not config.REGISTRO_ABIERTO:
        return Resultado(False, "El registro por cuenta propia está deshabilitado. "
                                "Solicite su acceso al área de sistemas.")
    nombre = (nombre or "").strip()
    if len(nombre) < 3:
        return Resultado(False, "Escriba su nombre completo.")
    try:
        correo = validar_correo(correo)
    except ValueError as e:
        return Resultado(False, str(e))
    if password != repetir:
        return Resultado(False, "Las contraseñas no coinciden.")
    errores = validar_politica(password)
    if errores:
        return Resultado(False, "La contraseña no cumple la política.", errores=errores)

    existente = consultar("SELECT id, estado FROM usuarios WHERE correo = %s", (correo,), uno=True)
    if existente:
        # Ni se confirma ni se niega. Si la cuenta está a medias, se reenvía el
        # código; si ya está en uso, se avisa a su dueño.
        if existente["estado"] == "PENDIENTE_CORREO":
            _emitir_codigo(existente["id"], correo, nombre)
        else:
            _avisar_intento_duplicado(existente["id"], correo)
        registrar_evento_seguridad("REGISTRO_DUPLICADO", correo, existente["id"],
                                   "Intento de registro sobre una cuenta existente")
        return Resultado(True, MENSAJE_ENVIADO, usuario_id=existente["id"])

    rol = config.REGISTRO_ROL_INICIAL or "SIN_ASIGNAR"
    nuevo = ejecutar(
        "INSERT INTO usuarios (nombre, correo, password_hash, rol, activo, estado, "
        "correo_verificado, debe_cambiar_password) VALUES (%s,%s,%s,%s,0,'PENDIENTE_CORREO',0,0)",
        (nombre, correo, hash_password(password), rol))
    registrar_evento_seguridad("REGISTRO_SOLICITADO", correo, nuevo, "Alta por cuenta propia")
    _emitir_codigo(nuevo, correo, nombre)
    return Resultado(True, MENSAJE_ENVIADO, usuario_id=nuevo)


def reenviar_codigo(usuario_id: int) -> Resultado:
    u = consultar("SELECT nombre, correo, estado, verificacion_enviado FROM usuarios WHERE id = %s",
                  (usuario_id,), uno=True)
    if not u or u["estado"] != "PENDIENTE_CORREO":
        return Resultado(False, MENSAJE_ENVIADO)
    ultimo = u["verificacion_enviado"]
    if ultimo and (datetime.now() - ultimo).total_seconds() < SEGUNDOS_ENTRE_ENVIOS:
        faltan = SEGUNDOS_ENTRE_ENVIOS - int((datetime.now() - ultimo).total_seconds())
        return Resultado(False, f"Espere {faltan} segundos antes de pedir otro código.")
    _emitir_codigo(usuario_id, u["correo"], u["nombre"])
    return Resultado(True, "Le enviamos un código nuevo. El anterior dejó de servir.")


def _emitir_codigo(usuario_id: int, correo: str, nombre: str):
    codigo = f"{secrets.randbelow(10 ** LONGITUD_CODIGO):0{LONGITUD_CODIGO}d}"
    ejecutar("UPDATE usuarios SET verificacion_hash = %s, verificacion_vence = %s, "
             "verificacion_intentos = 0, verificacion_enviado = NOW() WHERE id = %s",
             (hash_password(codigo), datetime.now() + timedelta(minutes=config.REGISTRO_MINUTOS_CODIGO),
              usuario_id))
    servicio_correo.enviar(
        destino=correo,
        asunto=f"Confirme su correo: {codigo}",
        titulo="Confirme su dirección de correo",
        cuerpo_html=_cuerpo_verificacion(nombre, codigo),
        pie="Si usted no solicitó esta cuenta, ignore este mensaje: sin el código no se "
            "activa nada. Este correo es automático; no lo responda.",
        etiqueta="REGISTRO")


def verificar_correo(usuario_id: int, codigo: str) -> Resultado:
    """Segundo paso: confirma que el buzón es de quien se registró."""
    codigo = "".join((codigo or "").split())
    u = consultar("SELECT nombre, correo, estado, verificacion_hash, verificacion_vence, "
                  "verificacion_intentos FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u or u["estado"] != "PENDIENTE_CORREO" or not u["verificacion_hash"]:
        return Resultado(False, "La solicitud no está vigente. Vuelva a registrarse.")
    if not u["verificacion_vence"] or u["verificacion_vence"] < datetime.now():
        return Resultado(False, "El código venció. Pida uno nuevo.")
    if u["verificacion_intentos"] >= MAX_INTENTOS:
        ejecutar("UPDATE usuarios SET verificacion_hash = NULL WHERE id = %s", (usuario_id,))
        registrar_evento_seguridad("REGISTRO_CODIGO_AGOTADO", u["correo"], usuario_id)
        return Resultado(False, "Demasiados intentos. Pida un código nuevo.")
    if not verificar_password(codigo, u["verificacion_hash"])[0]:
        ejecutar("UPDATE usuarios SET verificacion_intentos = verificacion_intentos + 1 "
                 "WHERE id = %s", (usuario_id,))
        return Resultado(False, "El código no es correcto.")

    automatico = bool(config.REGISTRO_ROL_INICIAL)
    ejecutar("UPDATE usuarios SET correo_verificado = 1, verificacion_hash = NULL, "
             "verificacion_vence = NULL, verificacion_intentos = 0, estado = %s, activo = %s "
             "WHERE id = %s",
             ("ACTIVO" if automatico else "PENDIENTE_APROBACION", 1 if automatico else 0, usuario_id))
    registrar_evento_seguridad("REGISTRO_VERIFICADO", u["correo"], usuario_id,
                               "Alta automática" if automatico else "Pendiente de autorización")
    if automatico:
        _avisar_cuenta_lista(usuario_id)
        return Resultado(True, "Su correo quedó confirmado y su cuenta está activa. Ya puede entrar.")
    return Resultado(True, "Su correo quedó confirmado. Un administrador debe autorizar su acceso; "
                           "le avisaremos por correo en cuanto ocurra.")


# ---------------------------------------------------------------------------
# Autorización por parte de un administrador
# ---------------------------------------------------------------------------
def pendientes() -> list[dict]:
    return consultar(
        "SELECT id, nombre, correo, fecha_creacion FROM usuarios "
        "WHERE estado = 'PENDIENTE_APROBACION' ORDER BY fecha_creacion")


def aprobar(admin: dict, usuario_id: int, rol: str) -> Resultado:
    from src.seguridad.permisos import ROLES
    if rol not in ROLES:
        return Resultado(False, "Ese rol no existe.")
    u = consultar("SELECT correo, estado FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u or u["estado"] != "PENDIENTE_APROBACION":
        return Resultado(False, "Esa solicitud ya no está pendiente.")
    ejecutar("UPDATE usuarios SET rol = %s, estado = 'ACTIVO', activo = 1, "
             "aprobado_por = %s, aprobado_en = NOW() WHERE id = %s", (rol, admin["id"], usuario_id))
    registrar_evento_seguridad("REGISTRO_APROBADO", u["correo"], usuario_id, f"Rol {rol}")
    registrar_log(admin["id"], "APROBAR_REGISTRO", "usuarios", usuario_id,
                  f"{u['correo']} autorizado con rol {rol}")
    _avisar_cuenta_lista(usuario_id)
    return Resultado(True, f"Cuenta autorizada con el rol {ROLES[rol][0]}.")


def rechazar(admin: dict, usuario_id: int, motivo: str = "") -> Resultado:
    u = consultar("SELECT correo, estado FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u or u["estado"] != "PENDIENTE_APROBACION":
        return Resultado(False, "Esa solicitud ya no está pendiente.")
    ejecutar("UPDATE usuarios SET estado = 'RECHAZADO', activo = 0, motivo_rechazo = %s, "
             "aprobado_por = %s, aprobado_en = NOW() WHERE id = %s",
             (motivo[:255] or None, admin["id"], usuario_id))
    registrar_evento_seguridad("REGISTRO_RECHAZADO", u["correo"], usuario_id, motivo[:200])
    registrar_log(admin["id"], "RECHAZAR_REGISTRO", "usuarios", usuario_id, motivo[:200])
    _avisar_rechazo(usuario_id, motivo)
    return Resultado(True, "Solicitud rechazada.")


# ---------------------------------------------------------------------------
# Correos
# ---------------------------------------------------------------------------
def _p(t: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:14.5px;line-height:1.65;color:#5A6167;">{t}</p>'


def _cuerpo_verificacion(nombre: str, codigo: str) -> str:
    return (
        _p(f"{nombre}, escriba este código en la pantalla de registro para confirmar "
           "que esta dirección es suya:")
        + f'<div style="margin:0 0 16px;padding:14px 18px;background:#F2F3F1;'
          f'border-left:3px solid #C1121F;font-family:Consolas,monospace;font-size:30px;'
          f'font-weight:700;letter-spacing:.18em;color:#12171C;text-align:center;">'
          f'{" ".join(codigo)}</div>'
        + _p(f"Vence en {config.REGISTRO_MINUTOS_CODIGO} minutos. Confirmar el correo no le da "
             "acceso al sistema todavía: primero un administrador debe autorizar su cuenta y "
             "asignarle un perfil."))


def _avisar_cuenta_lista(usuario_id: int):
    from src.seguridad.permisos import ROLES
    u = consultar("SELECT nombre, correo, rol FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u:
        return
    perfil = ROLES.get(u["rol"], (u["rol"],))[0]
    servicio_correo.enviar_en_segundo_plano(
        u["correo"], f"Su acceso a {config.CORREO_INSTITUCION} está listo", "Cuenta autorizada",
        _p(f'{u["nombre"]}, su cuenta ya está activa.')
        + _p(f'Perfil asignado: <strong style="color:#12171C;">{perfil}</strong>. '
             "Entre con el correo y la contraseña que escogió al registrarse.")
        + _p("Si su perfil maneja información crítica, el sistema le pedirá activar la "
             "verificación en dos pasos antes de dejarle operar."),
        etiqueta="REGISTRO_APROBADO")


def _avisar_rechazo(usuario_id: int, motivo: str):
    u = consultar("SELECT nombre, correo FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u:
        return
    servicio_correo.enviar_en_segundo_plano(
        u["correo"], "Sobre su solicitud de acceso", "Solicitud no autorizada",
        _p(f'{u["nombre"]}, su solicitud de acceso no fue autorizada.')
        + (_p(f"Motivo indicado: {motivo}") if motivo else "")
        + _p("Si cree que se trata de un error, comuníquese con el área de sistemas."),
        etiqueta="REGISTRO_RECHAZADO")


def _avisar_intento_duplicado(usuario_id: int, correo: str):
    """Alguien intentó registrarse con un correo que ya tiene cuenta.

    No se le dice al que lo intentó —sería confirmarle que la cuenta existe—, pero
    el dueño del buzón sí debe enterarse."""
    servicio_correo.enviar_en_segundo_plano(
        correo, "Intento de registro con su dirección", "Alguien intentó registrarse con su correo",
        _p("Recibimos una solicitud para crear una cuenta con esta dirección, que ya tiene "
           "una cuenta en el sistema. No hicimos ningún cambio.")
        + _p("Si fue usted y olvidó que ya estaba registrado, use la opción "
             "<strong style='color:#12171C;'>Olvidé mi contraseña</strong> en la pantalla de acceso.")
        + _p("Si no fue usted, alguien está probando direcciones. No tiene que hacer nada, "
             "pero conviene que su contraseña no se repita en otros sitios."),
        etiqueta="REGISTRO_DUPLICADO")
