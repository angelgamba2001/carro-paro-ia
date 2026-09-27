"""
Segundo factor enviado al correo, como alternativa a la aplicación de autenticación.

Es más cómodo (no hay que instalar nada) y más débil: el código viaja por la red y
quien controle el buzón controla el factor. Por eso:

  * los roles con permisos críticos siguen obligados a usar TOTP; el correo solo se
    ofrece a los demás, y como complemento cuando ya hay TOTP;
  * el código se guarda con bcrypt, igual que una contraseña, nunca en claro;
  * vence a los 10 minutos, es de un solo uso y se invalida al pedir otro;
  * cinco intentos fallidos lo anulan, y cuentan para el bloqueo de la cuenta;
  * el código nunca aparece en el log ni en la auditoría.

Seis dígitos dan un millón de combinaciones; con cinco intentos y diez minutos de
vigencia, adivinarlo tiene una probabilidad de 5 entre 10^6. Es el mismo orden que
usa la banca para este canal.
"""
import logging
import secrets
from datetime import datetime, timedelta

from src import config
from src.database.auditoria import registrar_evento_seguridad
from src.database.connection import consultar, ejecutar
from src.seguridad.contrasenas import hash_password, verificar_password

log = logging.getLogger(__name__)

LONGITUD = 6
# Cuánto hay que esperar entre un envío y el siguiente, para que nadie use el
# sistema como generador de correos hacia un tercero.
SEGUNDOS_ENTRE_ENVIOS = 60


def disponible(usuario_id: int) -> bool:
    """¿Esta cuenta tiene activado el canal de correo?"""
    u = consultar("SELECT mfa_correo_activo, activo FROM usuarios WHERE id = %s",
                  (usuario_id,), uno=True)
    return bool(u and u["activo"] and u["mfa_correo_activo"])


def activar(usuario_id: int, valor: bool = True):
    ejecutar("UPDATE usuarios SET mfa_correo_activo = %s WHERE id = %s", (1 if valor else 0, usuario_id))
    u = consultar("SELECT correo FROM usuarios WHERE id = %s", (usuario_id,), uno=True) or {}
    registrar_evento_seguridad("MFA_CORREO_ACTIVADO" if valor else "MFA_CORREO_DESACTIVADO",
                               u.get("correo"), usuario_id)


# ---------------------------------------------------------------------------
def enviar_codigo(usuario_id: int) -> tuple[bool, str]:
    """Genera un código, lo guarda cifrado y lo manda. Devuelve (ok, mensaje)."""
    u = consultar("SELECT correo, nombre, mfa_correo_enviado FROM usuarios WHERE id = %s",
                  (usuario_id,), uno=True)
    if not u:
        return False, "No fue posible enviar el código."

    ultimo = u["mfa_correo_enviado"]
    if ultimo and (datetime.now() - ultimo).total_seconds() < SEGUNDOS_ENTRE_ENVIOS:
        espera = SEGUNDOS_ENTRE_ENVIOS - int((datetime.now() - ultimo).total_seconds())
        return False, f"Ya se envió un código hace poco. Espere {espera} segundos para pedir otro."

    codigo = f"{secrets.randbelow(10 ** LONGITUD):0{LONGITUD}d}"
    vence = datetime.now() + timedelta(minutes=config.MFA_CORREO_MINUTOS)
    ejecutar("UPDATE usuarios SET mfa_correo_hash = %s, mfa_correo_vence = %s, "
             "mfa_correo_intentos = 0, mfa_correo_enviado = NOW() WHERE id = %s",
             (hash_password(codigo), vence, usuario_id))

    from src.servicios import correo as servicio_correo
    enviado = servicio_correo.enviar(
        destino=u["correo"],
        asunto=f"Su código de verificación: {codigo}",
        titulo="Código de verificación",
        cuerpo_html=_cuerpo(u["nombre"], codigo),
        pie="Si usted no intentó iniciar sesión, cambie su contraseña y avise al área de "
            "seguridad de la información. Este mensaje es automático; no lo responda.",
        etiqueta="MFA_CORREO",
    )
    registrar_evento_seguridad("MFA_CORREO_SOLICITADO", u["correo"], usuario_id,
                               "Código enviado" if enviado else "No se pudo enviar")
    if not enviado:
        return False, ("No fue posible enviar el código a su correo. Use su aplicación de "
                       "autenticación o comuníquese con soporte.")
    return True, f"Enviamos un código a {_ocultar(u['correo'])}. Vence en {config.MFA_CORREO_MINUTOS} minutos."


def verificar(usuario_id: int, codigo: str) -> bool:
    """Comprueba el código y lo consume. Un código válido solo sirve una vez."""
    codigo = "".join((codigo or "").split())
    if not codigo.isdigit() or len(codigo) != LONGITUD:
        return False
    u = consultar("SELECT correo, mfa_correo_hash, mfa_correo_vence, mfa_correo_intentos "
                  "FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u or not u["mfa_correo_hash"]:
        return False
    if not u["mfa_correo_vence"] or u["mfa_correo_vence"] < datetime.now():
        _limpiar(usuario_id)
        registrar_evento_seguridad("MFA_CORREO_VENCIDO", u["correo"], usuario_id)
        return False
    if u["mfa_correo_intentos"] >= config.MFA_CORREO_MAX_INTENTOS:
        _limpiar(usuario_id)
        registrar_evento_seguridad("MFA_CORREO_AGOTADO", u["correo"], usuario_id,
                                   "Se anuló el código por exceso de intentos")
        return False

    if not verificar_password(codigo, u["mfa_correo_hash"])[0]:
        ejecutar("UPDATE usuarios SET mfa_correo_intentos = mfa_correo_intentos + 1 WHERE id = %s",
                 (usuario_id,))
        return False

    _limpiar(usuario_id)                       # de un solo uso
    registrar_evento_seguridad("MFA_CORREO_VERIFICADO", u["correo"], usuario_id)
    return True


def _limpiar(usuario_id: int):
    ejecutar("UPDATE usuarios SET mfa_correo_hash = NULL, mfa_correo_vence = NULL, "
             "mfa_correo_intentos = 0 WHERE id = %s", (usuario_id,))


def _ocultar(correo: str) -> str:
    """m***o@dominio.com — confirma el buzón sin escribirlo entero en pantalla."""
    usuario, _, dom = (correo or "").partition("@")
    if len(usuario) <= 2:
        visible = usuario[:1] + "*"
    else:
        visible = f"{usuario[0]}{'*' * (len(usuario) - 2)}{usuario[-1]}"
    return f"{visible}@{dom}"


def _cuerpo(nombre: str, codigo: str) -> str:
    espaciado = " ".join(codigo)
    return f"""
<p style="margin:0 0 16px;font-size:14.5px;line-height:1.6;color:#5A6167;">
  {nombre}, use este código para completar su ingreso al sistema:
</p>
<div style="margin:0 0 16px;padding:14px 18px;background:#F2F3F1;border-left:3px solid #C1121F;
            font-family:Consolas,'Courier New',monospace;font-size:30px;font-weight:700;
            letter-spacing:.18em;color:#12171C;text-align:center;">{espaciado}</div>
<p style="margin:0;font-size:13px;line-height:1.6;color:#5A6167;">
  Vence en {config.MFA_CORREO_MINUTOS} minutos y solo puede usarse una vez.
  <strong style="color:#12171C;">Nadie del hospital le pedirá este código</strong>
  por teléfono, chat ni correo.
</p>"""
