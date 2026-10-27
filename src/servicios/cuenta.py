"""
Cambio del correo de una cuenta desde «Mi cuenta».

El correo es el usuario con el que se entra, así que cambiarlo equivale a cambiar de
identidad. Por eso:
  1. se pide la contraseña actual;
  2. se envía un código de un solo uso al correo NUEVO, para comprobar que la persona
     controla ese buzón (vence en 10 minutos, 5 intentos, se guarda con bcrypt);
  3. al confirmarlo se cambia el correo y se avisa al correo ANTERIOR;
  4. todo queda en eventos_seguridad y en el log de auditoría.
"""
import secrets
from datetime import datetime, timedelta

from src import config
from src.database.auditoria import registrar_evento_seguridad, registrar_log
from src.database.connection import consultar, ejecutar
from src.seguridad import correos
from src.seguridad.contrasenas import hash_password, verificar_password
from src.servicios import correo as servicio_correo
from src.servicios.errores import ErrorNegocio

MINUTOS = 10
MAX_INTENTOS = 5
ESPERA_SEGUNDOS = 60


def solicitar_cambio_correo(usuario_id: int, password: str, nuevo: str) -> str:
    """Envía el código al correo nuevo. Devuelve el mensaje para mostrar."""
    u = consultar("SELECT correo, nombre, password_hash FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not u or not verificar_password(password or "", u["password_hash"])[0]:
        registrar_evento_seguridad("CAMBIO_CORREO_FALLIDO", (u or {}).get("correo"), usuario_id,
                                   "Contraseña incorrecta")
        raise ErrorNegocio("La contraseña actual no es correcta.")
    try:
        nuevo = correos.validar(nuevo)
    except ValueError as e:
        raise ErrorNegocio(str(e)) from e
    if nuevo == u["correo"]:
        raise ErrorNegocio("El correo nuevo es igual al actual.")
    if consultar("SELECT 1 FROM usuarios WHERE correo = %s", (nuevo,), uno=True):
        raise ErrorNegocio("Ese correo ya está registrado en otra cuenta.")

    previo = consultar("SELECT creado FROM cambios_correo WHERE usuario_id = %s", (usuario_id,), uno=True)
    if previo and previo["creado"] and (datetime.now() - previo["creado"]).total_seconds() < ESPERA_SEGUNDOS:
        raise ErrorNegocio("Ya se envió un código hace un momento. Espere un minuto para pedir otro.")

    codigo = f"{secrets.randbelow(10 ** 6):06d}"
    ejecutar("REPLACE INTO cambios_correo (usuario_id, correo_nuevo, codigo_hash, vence, intentos, creado) "
             "VALUES (%s,%s,%s,%s,0,NOW())",
             (usuario_id, nuevo, hash_password(codigo), datetime.now() + timedelta(minutes=MINUTOS)))
    enviado = servicio_correo.enviar(
        destino=nuevo, asunto=f"Código para confirmar su nuevo correo: {codigo}",
        titulo="Confirme su nuevo correo",
        cuerpo_html=(f'<p style="font-size:14.5px;line-height:1.6;">{u["nombre"]}, este es el código para '
                     f'confirmar el cambio de correo de su cuenta:</p>'
                     f'<p style="font-size:28px;font-weight:700;letter-spacing:.18em;">{" ".join(codigo)}</p>'
                     f'<p style="font-size:13px;">Vence en {MINUTOS} minutos. Si usted no lo pidió, ignore este mensaje.</p>'),
        pie="Mensaje automático; no lo responda.", etiqueta="CAMBIO_CORREO")
    registrar_evento_seguridad("CAMBIO_CORREO_SOLICITADO", u["correo"], usuario_id,
                               "Código enviado" if enviado else "No se pudo enviar")
    if not enviado:
        raise ErrorNegocio("No fue posible enviar el código al correo nuevo. Intente más tarde.")
    return f"Enviamos un código a {nuevo}. Vence en {MINUTOS} minutos."


def confirmar_cambio_correo(usuario_id: int, codigo: str) -> str:
    """Valida el código y cambia el correo. Devuelve el correo nuevo."""
    p = consultar("SELECT correo_nuevo, codigo_hash, vence, intentos FROM cambios_correo WHERE usuario_id = %s",
                  (usuario_id,), uno=True)
    u = consultar("SELECT correo, nombre FROM usuarios WHERE id = %s", (usuario_id,), uno=True)
    if not p or not u:
        raise ErrorNegocio("No hay un cambio de correo pendiente. Solicite uno nuevo.")
    if p["vence"] < datetime.now() or p["intentos"] >= MAX_INTENTOS:
        ejecutar("DELETE FROM cambios_correo WHERE usuario_id = %s", (usuario_id,))
        raise ErrorNegocio("El código venció o se agotaron los intentos. Solicite uno nuevo.")
    codigo = "".join((codigo or "").split())
    if not codigo.isdigit() or not verificar_password(codigo, p["codigo_hash"])[0]:
        ejecutar("UPDATE cambios_correo SET intentos = intentos + 1 WHERE usuario_id = %s", (usuario_id,))
        registrar_evento_seguridad("CAMBIO_CORREO_FALLIDO", u["correo"], usuario_id, "Código incorrecto")
        raise ErrorNegocio("El código no es correcto.")
    if consultar("SELECT 1 FROM usuarios WHERE correo = %s AND id <> %s", (p["correo_nuevo"], usuario_id), uno=True):
        ejecutar("DELETE FROM cambios_correo WHERE usuario_id = %s", (usuario_id,))
        raise ErrorNegocio("Ese correo ya fue registrado por otra cuenta.")

    anterior, nuevo = u["correo"], p["correo_nuevo"]
    ejecutar("UPDATE usuarios SET correo = %s WHERE id = %s", (nuevo, usuario_id))
    ejecutar("DELETE FROM cambios_correo WHERE usuario_id = %s", (usuario_id,))
    registrar_evento_seguridad("CAMBIO_CORREO", nuevo, usuario_id, f"Antes: {anterior}")
    registrar_log(usuario_id, "CAMBIO_CORREO", "usuarios", usuario_id, f"{anterior} -> {nuevo}")
    servicio_correo.enviar_en_segundo_plano(
        destino=anterior, asunto="El correo de su cuenta fue cambiado", titulo="Cambio de correo",
        cuerpo_html=(f'<p style="font-size:14.5px;line-height:1.6;">{u["nombre"]}, el correo de su cuenta en '
                     f'{config.CORREO_INSTITUCION} cambió a <strong>{nuevo}</strong>. Si usted no hizo este '
                     f'cambio, avise de inmediato al área de seguridad de la información.</p>'),
        pie="Mensaje automático; no lo responda.", etiqueta="CAMBIO_CORREO_AVISO")
    return nuevo
