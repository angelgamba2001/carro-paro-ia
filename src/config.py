"""Configuración central. Todo valor sensible sale de variables de entorno (.env)."""
import os
from pathlib import Path
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")


def _int(nombre: str, defecto: int) -> int:
    try:
        return int(os.getenv(nombre, defecto))
    except ValueError:
        return defecto


# --- Base de datos ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = _int("DB_PORT", 3306)
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "carro_paro_db")

# --- Seguridad (valores heredados de SGHCU) ---
MAX_INTENTOS_LOGIN = _int("MAX_INTENTOS_LOGIN", 5)
MINUTOS_BLOQUEO = _int("MINUTOS_BLOQUEO", 15)
MINUTOS_INACTIVIDAD = _int("MINUTOS_INACTIVIDAD", 15)
JWT_SECRETO = os.getenv("JWT_SECRETO", "")
JWT_MINUTOS_EXPIRACION = _int("JWT_MINUTOS_EXPIRACION", 30)
ENTORNO = os.getenv("ENTORNO", "desarrollo")  # desarrollo | produccion

# Una sola sesión web activa por persona: al entrar desde otro lugar, la anterior se cierra
# y queda registrado. Con 0 se permiten sesiones simultáneas (cada una sigue siendo revocable).
SESION_UNICA = os.getenv("SESION_UNICA", "1").strip().lower() in ("1", "true", "si", "sí", "yes")
# Clave Fernet (32 bytes en base64 url-safe) con la que se cifra el secreto del segundo factor.
# Generar:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Si se omite se deriva de JWT_SECRETO; en producción debe existir alguna de las dos.
CLAVE_CIFRADO = os.getenv("CLAVE_CIFRADO", "")


def _bool(nombre: str, defecto: bool = False) -> bool:
    return os.getenv(nombre, str(defecto)).strip().lower() in ("1", "true", "si", "sí", "yes")


# --- Identidad institucional y correo ---
# Dominios admitidos al crear usuarios. Vacío = cualquier dominio válido.
#   Ejemplo:  DOMINIOS_CORREO=husanrafael.co,unipamplona.edu.co
DOMINIOS_CORREO = os.getenv("DOMINIOS_CORREO", "")
CORREO_INSTITUCION = os.getenv("CORREO_INSTITUCION", "Hospital Universitario San Rafael")
CORREO_MODO = os.getenv("CORREO_MODO", "archivo")      # smtp | archivo | desactivado
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com")
SMTP_PUERTO = _int("SMTP_PUERTO", 587)
SMTP_SSL = _bool("SMTP_SSL", False)                    # False = STARTTLS (587); True = SSL (465)
SMTP_USUARIO = os.getenv("SMTP_USUARIO", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_TIMEOUT = _int("SMTP_TIMEOUT", 20)
CORREO_REMITENTE = os.getenv("CORREO_REMITENTE", "")   # si se omite, se usa SMTP_USUARIO

# Segundo factor enviado por correo (alternativa al TOTP)
MFA_CORREO_MINUTOS = _int("MFA_CORREO_MINUTOS", 10)
MFA_CORREO_MAX_INTENTOS = _int("MFA_CORREO_MAX_INTENTOS", 5)
# Segundo factor con la aplicación de autenticación (TOTP)
#   MFA_VENTANA: códigos vecinos que se aceptan (1 = ±30 s de desfase de reloj; 0 = solo el actual)
#   MFA_PENDIENTE_MINUTOS: cuánto puede esperar la pantalla del código antes de volver al inicio
MFA_VENTANA = max(0, min(2, _int("MFA_VENTANA", 1)))
MFA_PENDIENTE_MINUTOS = max(1, _int("MFA_PENDIENTE_MINUTOS", 5))

# --- Inicio de sesión con Microsoft (Entra ID / Azure AD) ---
MS_CLIENT_ID = os.getenv("MS_CLIENT_ID", "")
MS_TENANT_ID = os.getenv("MS_TENANT_ID", "common")
MS_CLIENT_SECRET = os.getenv("MS_CLIENT_SECRET", "")
MS_REDIRECT_URI = os.getenv("MS_REDIRECT_URI", "http://localhost:8501")
# Si un correo de Microsoft no existe en la BD: rechazarlo o crear la cuenta con este rol
MS_ROL_POR_DEFECTO = os.getenv("MS_ROL_POR_DEFECTO", "")

# --- Registro de usuarios por cuenta propia ---
REGISTRO_ABIERTO = _bool("REGISTRO_ABIERTO", True)
# Vacío = la cuenta queda esperando que un administrador le asigne el rol.
# Con un rol = se activa sola al verificar el correo. Use el de menos privilegios.
REGISTRO_ROL_INICIAL = os.getenv("REGISTRO_ROL_INICIAL", "")
REGISTRO_MINUTOS_CODIGO = _int("REGISTRO_MINUTOS_CODIGO", 20)

# --- API: orígenes autorizados (app móvil) ---
# Cordova sirve la app desde https://localhost en Android y capacitor://localhost en iOS.
# Nunca use "*": eso permitiría que cualquier sitio web llame a la API con el token.
CORS_ORIGENES = os.getenv(
    "CORS_ORIGENES",
    "https://localhost,http://localhost,capacitor://localhost,ionic://localhost")

# --- Reglas de negocio ---
DIAS_PROXIMO_VENCER = _int("DIAS_PROXIMO_VENCER", 30)
HORIZONTE_PREDICCION_DIAS = _int("HORIZONTE_PREDICCION_DIAS", 14)

# --- Data lake (Big Data) ---
DATA_DIR = Path(os.getenv("DATA_DIR", RAIZ / "data"))
RAW_DIR = DATA_DIR / "raw"
BRONZE_DIR = DATA_DIR / "bronze"
SILVER_DIR = DATA_DIR / "silver"
GOLD_DIR = DATA_DIR / "gold"
REFERENCIA_DIR = DATA_DIR / "referencia"
MOTOR_BIGDATA = os.getenv("MOTOR_BIGDATA", "spark")  # spark | pandas
CUM_API_URL = os.getenv("CUM_API_URL", "https://www.datos.gov.co/resource/i7cb-raxc.json")

# --- Agente IA ---
AGENTE_PROVEEDOR = os.getenv("AGENTE_PROVEEDOR", "reglas")  # reglas | huggingface | anthropic
HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_MODELO = os.getenv("HF_MODELO", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# LLM con API compatible con OpenAI (Ollama local, Hugging Face, Groq...)
LLM_URL = os.getenv("LLM_URL", "http://localhost:11434/v1")
LLM_MODELO = os.getenv("LLM_MODELO", "qwen3:8b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TIMEOUT = _int("LLM_TIMEOUT", 180)
