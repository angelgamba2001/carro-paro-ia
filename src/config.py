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
LLM_MODELO = os.getenv("LLM_MODELO", "qwen2.5:7b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_TIMEOUT = _int("LLM_TIMEOUT", 180)
