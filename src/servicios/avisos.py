"""
Avisos que el sistema envía por correo ante hechos de seguridad.

Qué se avisa y por qué:
  * cuenta creada      — la persona necesita saber que existe y con qué entrar;
  * cuenta bloqueada   — si el bloqueo no lo causó ella, alguien está probando
                         contraseñas contra su cuenta y debe enterarse;
  * contraseña cambiada— el aviso es lo que convierte un cambio no autorizado en
                         un incidente detectado en minutos y no en meses.

Lo que NO se envía: contraseñas, códigos de verificación ni enlaces con permisos.
La contraseña inicial se entrega por el canal que defina la institución, no aquí.

Todos los envíos van en segundo plano: un servidor de correo lento no puede
retrasar un inicio de sesión ni dejar a medias la creación de un usuario.
"""
from datetime import datetime

from src import config
from src.database.connection import consultar
from src.servicios import correo as servicio_correo

SUAVE, TINTA = "#5A6167", "#12171C"


def _p(texto: str) -> str:
    return f'<p style="margin:0 0 14px;font-size:14.5px;line-height:1.65;color:{SUAVE};">{texto}</p>'


def _datos(usuario_id: int) -> dict | None:
    return consultar("SELECT nombre, correo, rol FROM usuarios WHERE id = %s", (usuario_id,), uno=True)


def _ficha(filas: list[tuple[str, str]]) -> str:
    """Tabla de dos columnas con los datos del evento."""
    celdas = "".join(
        f'<tr><td style="padding:5px 14px 5px 0;font-size:12.5px;color:{SUAVE};'
        f'white-space:nowrap;vertical-align:top;">{k}</td>'
        f'<td style="padding:5px 0;font-size:13px;color:{TINTA};">{v}</td></tr>'
        for k, v in filas)
    return ('<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin:0 0 16px;border-top:1px solid #D4D7D2;border-bottom:1px solid #D4D7D2;'
            f'width:100%;">{celdas}</table>')


# ---------------------------------------------------------------------------
def cuenta_creada(usuario_id: int, creada_por: str = ""):
    u = _datos(usuario_id)
    if not u:
        return
    from src.seguridad.permisos import ROLES
    rol = ROLES.get(u["rol"], (u["rol"],))[0]
    cuerpo = (
        _p(f'{u["nombre"]}, se creó su cuenta en el sistema de control de carros de paro '
           f'de {config.CORREO_INSTITUCION}.')
        + _ficha([("Usuario", u["correo"]), ("Perfil", rol),
                  ("Creada por", creada_por or "el área de sistemas"),
                  ("Fecha", f"{datetime.now():%d/%m/%Y %H:%M}")])
        + _p("La contraseña inicial se la entrega el área de sistemas por separado. "
             "<strong>Deberá cambiarla la primera vez que entre</strong>, y el sistema no le "
             "permitirá continuar hasta que lo haga.")
        + _p("Si su perfil maneja información crítica, también tendrá que activar la "
             "verificación en dos pasos antes de poder operar."))
    servicio_correo.enviar_en_segundo_plano(
        u["correo"], f"Su cuenta en {config.CORREO_INSTITUCION}", "Cuenta creada",
        cuerpo, etiqueta="CUENTA_CREADA")


def cuenta_bloqueada(usuario_id: int, motivo: str = ""):
    u = _datos(usuario_id)
    if not u:
        return
    cuerpo = (
        _p(f'{u["nombre"]}, su cuenta quedó bloqueada temporalmente por seguridad.')
        + _ficha([("Motivo", motivo or "intentos de ingreso fallidos"),
                  ("Duración", f"{config.MINUTOS_BLOQUEO} minutos"),
                  ("Momento", f"{datetime.now():%d/%m/%Y %H:%M}")])
        + _p("Si fue usted quien se equivocó al escribir la contraseña, no tiene que hacer nada: "
             "podrá intentarlo de nuevo cuando pase ese tiempo.")
        + _p("<strong>Si no fue usted</strong>, alguien está probando contraseñas contra su "
             "cuenta. Avise cuanto antes al área de seguridad de la información."))
    servicio_correo.enviar_en_segundo_plano(
        u["correo"], "Su cuenta fue bloqueada temporalmente", "Cuenta bloqueada",
        cuerpo, etiqueta="BLOQUEO")


def password_cambiada(usuario_id: int, via: str = "el cambio de contraseña"):
    u = _datos(usuario_id)
    if not u:
        return
    cuerpo = (
        _p(f'{u["nombre"]}, la contraseña de su cuenta acaba de cambiar.')
        + _ficha([("Cuenta", u["correo"]), ("Vía", via),
                  ("Momento", f"{datetime.now():%d/%m/%Y %H:%M}")])
        + _p("Si usted hizo el cambio, este mensaje es solo una constancia.")
        + _p("<strong>Si no reconoce este cambio</strong>, su cuenta está comprometida: "
             "comuníquese de inmediato con el área de seguridad de la información."))
    servicio_correo.enviar_en_segundo_plano(
        u["correo"], "Su contraseña fue modificada", "Contraseña modificada",
        cuerpo, etiqueta="CAMBIO_PASSWORD")
