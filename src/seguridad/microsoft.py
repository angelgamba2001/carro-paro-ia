"""
Inicio de sesión con la cuenta de Microsoft (Entra ID, antes Azure AD).

Flujo: OpenID Connect con authorization code + PKCE. El usuario va a Microsoft,
se autentica allá —con la política de la institución, incluido su propio MFA— y
vuelve con un código de un solo uso que el servidor canjea por el token. La
contraseña nunca pasa por este sistema.

Por qué PKCE aunque haya secreto de cliente: el canje ocurre en el servidor, pero
Streamlit devuelve el código en la barra de direcciones, donde queda expuesto al
historial y a las extensiones del navegador. Con PKCE, un código robado allí no
sirve sin el verificador, que nunca sale del servidor.

Decisiones deliberadas:
  * Se valida el `state` para cortar CSRF sobre el propio inicio de sesión.
  * El usuario se identifica por `oid`, no por correo: el correo puede cambiar
    (matrimonio, cambio de dependencia) y el oid no.
  * Una identidad de Microsoft NO crea cuentas por sí sola, salvo que se configure
    MS_ROL_POR_DEFECTO. Sin eso, quien no esté dado de alta no entra, que es lo
    correcto en un sistema donde el rol determina qué se puede tocar.
  * El correo verificado de Microsoft vincula la cuenta existente la primera vez;
    a partir de ahí manda el oid.
"""
import base64
import hashlib
import logging
import secrets
import urllib.parse

from src import config
from src.database.auditoria import registrar_evento_seguridad
from src.database.connection import consultar, ejecutar

log = logging.getLogger(__name__)

ALCANCE = "openid profile email User.Read"
TIEMPO_ESPERA = 15


def configurado() -> bool:
    """¿Hay datos suficientes para intentar el SSO?"""
    return bool(config.MS_CLIENT_ID and config.MS_CLIENT_SECRET and config.MS_TENANT_ID)


def _base() -> str:
    return f"https://login.microsoftonline.com/{config.MS_TENANT_ID}/oauth2/v2.0"


# ---------------------------------------------------------------------------
def preparar() -> dict:
    """Genera state y el par PKCE. Lo devuelto se guarda en la sesión del servidor."""
    verificador = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    reto = base64.urlsafe_b64encode(
        hashlib.sha256(verificador.encode()).digest()).decode().rstrip("=")
    return {"state": secrets.token_urlsafe(32), "verificador": verificador, "reto": reto}


def url_de_ingreso(preparacion: dict) -> str:
    parametros = {
        "client_id": config.MS_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": config.MS_REDIRECT_URI,
        "response_mode": "query",
        "scope": ALCANCE,
        "state": preparacion["state"],
        "code_challenge": preparacion["reto"],
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{_base()}/authorize?" + urllib.parse.urlencode(parametros)


def canjear_codigo(codigo: str, verificador: str) -> dict:
    """Cambia el código por los datos de la persona. Levanta RuntimeError si falla."""
    import requests
    respuesta = requests.post(
        f"{_base()}/token",
        data={"client_id": config.MS_CLIENT_ID,
              "client_secret": config.MS_CLIENT_SECRET,
              "code": codigo,
              "redirect_uri": config.MS_REDIRECT_URI,
              "grant_type": "authorization_code",
              "code_verifier": verificador,
              "scope": ALCANCE},
        timeout=TIEMPO_ESPERA,
    )
    if respuesta.status_code != 200:
        detalle = respuesta.json().get("error_description", respuesta.text)[:200]
        raise RuntimeError(f"Microsoft rechazó el código: {detalle}")

    token = respuesta.json().get("access_token")
    if not token:
        raise RuntimeError("Microsoft no devolvió un token de acceso.")

    perfil = requests.get("https://graph.microsoft.com/v1.0/me",
                          headers={"Authorization": f"Bearer {token}"},
                          timeout=TIEMPO_ESPERA)
    if perfil.status_code != 200:
        raise RuntimeError("No fue posible leer el perfil en Microsoft Graph.")
    d = perfil.json()
    correo = (d.get("mail") or d.get("userPrincipalName") or "").strip().lower()
    if not correo:
        raise RuntimeError("La cuenta de Microsoft no expone un correo utilizable.")
    return {"oid": d.get("id", ""), "correo": correo,
            "nombre": d.get("displayName") or correo.partition("@")[0]}


# ---------------------------------------------------------------------------
def resolver_usuario(identidad: dict) -> tuple[dict | None, str]:
    """Traduce la identidad de Microsoft a un usuario del sistema.

    Devuelve (usuario, mensaje). Usuario None significa que no puede entrar.
    """
    from src.seguridad.correos import dominios_permitidos, dominio

    oid, correo = identidad.get("oid", ""), identidad["correo"]
    permitidos = dominios_permitidos()
    if permitidos and dominio(correo) not in permitidos:
        registrar_evento_seguridad("SSO_RECHAZADO", correo, detalle="Dominio no permitido",
                                   origen="MICROSOFT")
        return None, "Esa cuenta no pertenece a un dominio autorizado para este sistema."

    u = None
    if oid:
        u = consultar("SELECT id, activo FROM usuarios WHERE ms_oid = %s", (oid,), uno=True)
    if not u:
        # Primera vez: se vincula por el correo que Microsoft ya verificó
        u = consultar("SELECT id, activo FROM usuarios WHERE correo = %s", (correo,), uno=True)
        if u and oid:
            ejecutar("UPDATE usuarios SET ms_oid = %s WHERE id = %s", (oid, u["id"]))
            registrar_evento_seguridad("SSO_VINCULADO", correo, u["id"],
                                       "Cuenta asociada a la identidad de Microsoft", "MICROSOFT")

    if not u:
        if not config.MS_ROL_POR_DEFECTO:
            registrar_evento_seguridad("SSO_RECHAZADO", correo,
                                       detalle="Sin cuenta en el sistema", origen="MICROSOFT")
            return None, ("Su cuenta de Microsoft es válida, pero no está dada de alta en el "
                          "sistema. Solicite el acceso al área de sistemas.")
        u = {"id": _crear_desde_sso(identidad), "activo": 1}

    if not u["activo"]:
        registrar_evento_seguridad("SSO_RECHAZADO", correo, u["id"], "Usuario inactivo", "MICROSOFT")
        return None, "Su cuenta está inactiva. Comuníquese con el área de sistemas."

    from src.seguridad.autenticacion import revalidar_usuario
    usuario = revalidar_usuario(u["id"])
    ejecutar("UPDATE usuarios SET ultimo_acceso = NOW(), ultimo_acceso_origen = 'MICROSOFT', "
             "intentos_fallidos = 0, bloqueado_hasta = NULL WHERE id = %s", (u["id"],))
    registrar_evento_seguridad("LOGIN_OK", correo, u["id"], "Inicio con Microsoft", "MICROSOFT")
    return usuario, ""


def _crear_desde_sso(identidad: dict) -> int:
    """Alta automática. Solo ocurre si MS_ROL_POR_DEFECTO está configurado.

    Se crea sin contraseña utilizable: quien entra por SSO no necesita una, y
    dejar una en blanco sería peor que no tenerla.
    """
    import secrets as _s
    from src.seguridad.contrasenas import hash_password
    nuevo = ejecutar(
        "INSERT INTO usuarios (nombre, correo, password_hash, rol, ms_oid, debe_cambiar_password) "
        "VALUES (%s,%s,%s,%s,%s,0)",
        (identidad["nombre"], identidad["correo"], hash_password(_s.token_urlsafe(48)),
         config.MS_ROL_POR_DEFECTO, identidad.get("oid") or None))
    registrar_evento_seguridad("SSO_ALTA_AUTOMATICA", identidad["correo"], nuevo,
                               f"Creado con rol {config.MS_ROL_POR_DEFECTO}", "MICROSOFT")
    return nuevo


def diagnostico() -> dict:
    return {"configurado": configurado(),
            "tenant": config.MS_TENANT_ID if configurado() else "—",
            "cliente": (config.MS_CLIENT_ID[:8] + "…") if config.MS_CLIENT_ID else "—",
            "retorno": config.MS_REDIRECT_URI,
            "alta_automatica": config.MS_ROL_POR_DEFECTO or "no (solo cuentas ya creadas)"}
