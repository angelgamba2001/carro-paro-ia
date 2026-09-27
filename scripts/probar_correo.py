"""
Comprueba la configuración de correo y, si procede, envía un mensaje de prueba.

    python scripts/probar_correo.py                       # solo diagnóstico
    python scripts/probar_correo.py destino@dominio.com   # además, envía

Traduce los errores de Microsoft y Google a la causa real y a qué hacer, porque
sus mensajes originales son crípticos y llevan a buscar en el sitio equivocado.
"""
import smtplib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config                                    # noqa: E402
from src.seguridad import microsoft                       # noqa: E402
from src.servicios import correo                          # noqa: E402

CAUSAS = [
    ("smtpclientauthentication is disabled",
     "El buzón tiene deshabilitado el envío por SMTP.",
     ["Microsoft lo desactiva por defecto desde 2022, por seguridad.",
      "Pida a TI que habilite SMTP AUTH para ESE buzón (se hace uno por uno).",
      "Mientras tanto, CORREO_MODO=archivo le deja seguir trabajando.",
      "Detalle en docs/CORREO_Y_SSO.md, apartado 2."]),
    ("authentication unsuccessful",
     "Usuario o contraseña incorrectos para el servidor de correo.",
     ["Revise SMTP_USUARIO y SMTP_PASSWORD en el .env.",
      "Si la cuenta tiene verificación en dos pasos, una contraseña normal NO sirve:",
      "hay que generar una contraseña de aplicación."]),
    ("application-specific password",
     "Gmail exige una contraseña de aplicación.",
     ["Cuenta de Google -> Seguridad -> Verificación en dos pasos -> Contraseñas de aplicaciones.",
      "Use esos 16 caracteres como SMTP_PASSWORD."]),
    ("5.7.57", "El servidor exige autenticarse antes de enviar.",
     ["Falta SMTP_USUARIO o SMTP_PASSWORD en el .env."]),
    ("username and password not accepted",
     "Gmail rechazó la clave: está usando la contraseña normal de la cuenta.",
     ["Gmail NO acepta la contraseña con la que usted entra a su correo.",
      "Active la verificación en dos pasos en su cuenta de Google y genere una",
      "contraseña de aplicación de 16 caracteres: myaccount.google.com/apppasswords",
      "Esos 16 caracteres, sin espacios, van en SMTP_PASSWORD."]),
]


def explicar(error: Exception):
    texto = str(error).lower()
    for patron, titulo, pasos in CAUSAS:
        if patron in texto:
            print(f"\n  Causa: {titulo}")
            for i, p in enumerate(pasos, 1):
                print(f"    {i}. {p}")
            return
    print("\n  No reconozco este error. El mensaje completo está arriba.")


def main():
    d = correo.diagnostico()
    print("CORREO")
    print(f"  Modo          {d['modo']}")
    print(f"  Servidor      {d['servidor']}")
    print(f"  Remitente     {d['remitente']}")
    if d["modo"] == "archivo":
        print(f"  Carpeta       {d['carpeta']}")
    print(f"  Configurado   {'sí' if d['listo'] else 'NO: faltan credenciales en el .env'}")

    s = microsoft.diagnostico()
    print("\nINICIO DE SESIÓN CON MICROSOFT")
    print(f"  Configurado   {'sí' if s['configurado'] else 'no (el botón no aparecerá)'}")
    if s["configurado"]:
        print(f"  Inquilino     {s['tenant']}")
        print(f"  Cliente       {s['cliente']}")
        print(f"  URI retorno   {s['retorno']}")
        print(f"  Alta autom.   {s['alta_automatica']}")

    print("\nDOMINIOS ADMITIDOS AL CREAR USUARIOS")
    from src.seguridad.correos import dominios_permitidos
    permitidos = dominios_permitidos()
    print("  " + (", ".join("@" + p for p in permitidos) if permitidos
                  else "cualquiera (DOMINIOS_CORREO está vacío)"))

    destino = sys.argv[1] if len(sys.argv) > 1 else None
    if not destino:
        print("\nPara enviar una prueba:  python scripts/probar_correo.py su@correo.com")
        return 0

    print(f"\nEnviando a {destino}…")
    try:
        ok = correo.enviar(
            destino, "Prueba de configuración · SMARTDATA 360",
            "La configuración de correo funciona",
            '<p style="margin:0 0 14px;font-size:14.5px;line-height:1.65;color:#5A6167;">'
            "Si está leyendo esto, el sistema ya puede enviar avisos de seguridad y "
            "códigos de verificación a los usuarios.</p>",
            etiqueta="PRUEBA")
    except Exception as e:                                 # noqa: BLE001
        print(f"  FALLÓ: {e}")
        explicar(e)
        return 1

    if not ok and d["modo"] == "smtp":
        print("  No salió. Revise el registro de la aplicación para ver el motivo.")
        return 1
    if d["modo"] == "archivo":
        ultimo = sorted(correo.SALIENTE.glob("*.html"))[-1]
        print(f"  Guardado en {ultimo}")
        print("  Ábralo con doble clic para ver cómo le llegaría al usuario.")
    else:
        print("  Enviado. Revise la bandeja de entrada y la carpeta de correo no deseado.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except smtplib.SMTPException as e:
        print(f"Error de SMTP: {e}")
        explicar(e)
        raise SystemExit(1) from e
