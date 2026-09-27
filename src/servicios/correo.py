"""
Envío de correo institucional.

Tres modos, en CORREO_MODO del .env:

  smtp         Envía de verdad por el servidor de la institución (Microsoft 365,
               Google Workspace o el que sea). Requiere credenciales.
  archivo      No envía nada: guarda cada mensaje como .html en data/correo_saliente
               y lo puede abrir con el navegador. Es el modo por defecto, sirve para
               desarrollar y para sustentar sin depender de la red.
  desactivado  No hace nada. Para pruebas automatizadas.

El envío NUNCA interrumpe la operación. Si el servidor de correo no responde, se
registra el fallo y la acción del usuario continúa: no tendría sentido impedir un
restablecimiento de contraseña porque el buzón esté caído. Quien necesite saber si
un mensaje salió, lo consulta en eventos_seguridad.
"""
import logging
import re
import smtplib
import ssl
import threading
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from src import config

log = logging.getLogger(__name__)

SALIENTE = config.DATA_DIR / "correo_saliente"

# Paleta del sistema, en línea: los clientes de correo descartan las hojas de estilo
TINTA, SUAVE, LINEA, CARRO, PAPEL = "#12171C", "#5A6167", "#D4D7D2", "#C1121F", "#F2F3F1"


def _plantilla(titulo: str, cuerpo_html: str, pie: str = "") -> str:
    """Una tabla y estilos en línea, que es lo único que Outlook renderiza igual."""
    return f"""\
<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{titulo}</title></head>
<body style="margin:0;padding:24px 12px;background:{PAPEL};
             font-family:'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{TINTA};">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"
       style="max-width:560px;margin:0 auto;background:#fff;border:1px solid {LINEA};">
  <tr><td style="padding:20px 28px 16px;border-bottom:2px solid {CARRO};">
    <div style="font-size:15px;font-weight:600;letter-spacing:-.01em;">{config.CORREO_INSTITUCION}</div>
    <div style="font-size:12px;color:{SUAVE};margin-top:2px;">SMARTDATA 360 · Carro de Paro</div>
  </td></tr>
  <tr><td style="padding:26px 28px 22px;">
    <h1 style="margin:0 0 14px;font-size:20px;line-height:1.25;font-weight:600;">{titulo}</h1>
    {cuerpo_html}
  </td></tr>
  <tr><td style="padding:14px 28px 20px;border-top:1px solid {LINEA};
                 font-size:11.5px;color:{SUAVE};line-height:1.55;">
    {pie or "Mensaje automático del sistema de control de medicamentos de reanimación. "
            "No responda a esta dirección."}
  </td></tr>
</table>
</body></html>"""


def _a_texto(html: str) -> str:
    """Versión en texto plano. Algunos clientes corporativos bloquean el HTML."""
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>", "\n", html)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


# ---------------------------------------------------------------------------
def enviar(destino: str, asunto: str, titulo: str, cuerpo_html: str,
           pie: str = "", etiqueta: str = "") -> bool:
    """Envía un mensaje. Devuelve si salió; nunca levanta excepción.

    `etiqueta` es lo que se registra en la auditoría (por ejemplo MFA o BLOQUEO).
    El contenido del mensaje NO se registra: un código de verificación en el log
    valdría tanto como no tenerlo.
    """
    html = _plantilla(titulo, cuerpo_html, pie)
    modo = (config.CORREO_MODO or "archivo").lower()
    try:
        if modo == "desactivado":
            return False
        if modo == "archivo":
            return _a_archivo(destino, asunto, html, etiqueta)
        return _por_smtp(destino, asunto, html)
    except Exception as e:                                   # noqa: BLE001
        log.error("No se pudo enviar el correo a %s (%s): %s", destino, etiqueta, e)
        _registrar("CORREO_FALLIDO", destino, f"{etiqueta or asunto}: {type(e).__name__}")
        return False


def enviar_en_segundo_plano(*args, **kwargs):
    """Igual que enviar(), sin hacer esperar a quien está frente a la pantalla.

    El SMTP de Microsoft tarda entre uno y tres segundos; bloquear la interfaz ese
    rato en cada inicio de sesión se nota. El resultado queda en la auditoría.
    """
    threading.Thread(target=enviar, args=args, kwargs=kwargs, daemon=True).start()


def _a_archivo(destino: str, asunto: str, html: str, etiqueta: str) -> bool:
    SALIENTE.mkdir(parents=True, exist_ok=True)
    seguro = re.sub(r"[^A-Za-z0-9.@_-]", "_", destino)
    nombre = f"{datetime.now():%Y%m%d-%H%M%S}-{seguro}.html"
    encabezado = (f'<!-- Para: {destino} | Asunto: {asunto} | '
                  f'Generado: {datetime.now():%Y-%m-%d %H:%M:%S} -->\n')
    (SALIENTE / nombre).write_text(encabezado + html, encoding="utf-8")
    log.info("Correo guardado en %s (modo archivo)", SALIENTE / nombre)
    _registrar("CORREO_SIMULADO", destino, f"{etiqueta or asunto} -> {nombre}")
    return True


def _por_smtp(destino: str, asunto: str, html: str) -> bool:
    if not config.SMTP_HOST or not config.SMTP_USUARIO:
        raise RuntimeError("Faltan SMTP_HOST o SMTP_USUARIO en el .env")

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = formataddr((config.CORREO_INSTITUCION, config.CORREO_REMITENTE or config.SMTP_USUARIO))
    msg["To"] = destino
    msg["Message-ID"] = make_msgid(domain=(config.CORREO_REMITENTE or "localhost").rpartition("@")[2])
    msg["Auto-Submitted"] = "auto-generated"          # evita respuestas automáticas en cadena
    msg.set_content(_a_texto(html))
    msg.add_alternative(html, subtype="html")

    contexto = ssl.create_default_context()
    if config.SMTP_SSL:                                # puerto 465, TLS desde el principio
        with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PUERTO, context=contexto,
                              timeout=config.SMTP_TIMEOUT) as s:
            s.login(config.SMTP_USUARIO, config.SMTP_PASSWORD)
            s.send_message(msg)
    else:                                              # puerto 587, STARTTLS (Microsoft 365)
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PUERTO, timeout=config.SMTP_TIMEOUT) as s:
            s.ehlo()
            s.starttls(context=contexto)
            s.ehlo()
            s.login(config.SMTP_USUARIO, config.SMTP_PASSWORD)
            s.send_message(msg)
    _registrar("CORREO_ENVIADO", destino, asunto)
    return True


def _registrar(tipo: str, destino: str, detalle: str):
    try:
        from src.database.auditoria import registrar_evento_seguridad
        registrar_evento_seguridad(tipo, destino, detalle=detalle[:255])
    except Exception:                                   # noqa: BLE001
        log.debug("No se pudo registrar el evento de correo", exc_info=True)


def diagnostico() -> dict:
    """Estado de la configuración, para la pantalla de administración y los scripts."""
    modo = (config.CORREO_MODO or "archivo").lower()
    return {
        "modo": modo,
        "listo": modo == "archivo" or modo == "desactivado"
                 or bool(config.SMTP_HOST and config.SMTP_USUARIO and config.SMTP_PASSWORD),
        "servidor": f"{config.SMTP_HOST}:{config.SMTP_PUERTO}" if config.SMTP_HOST else "—",
        "remitente": config.CORREO_REMITENTE or config.SMTP_USUARIO or "—",
        "carpeta": str(SALIENTE) if modo == "archivo" else "—",
    }
