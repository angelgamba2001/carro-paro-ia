"""
Voz del agente (opcional): audio -> texto con Whisper local y texto -> audio con edge-tts.
    pip install faster-whisper edge-tts
Whisper corre en el equipo (el audio no sale). edge-tts envía SOLO el texto de la respuesta
al servicio de voz de Microsoft; para voz 100 % local se puede reemplazar por pyttsx3.
"""
import asyncio
import importlib.util
import io
import re
from functools import lru_cache

VOZ = "es-CO-SalomeNeural"      # alternativa masculina: es-CO-GonzaloNeural
MODELO_WHISPER = "small"        # "base" es más liviano; "medium" más preciso


def voz_disponible() -> bool:
    return all(importlib.util.find_spec(m) for m in ("faster_whisper", "edge_tts"))


@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel
    return WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")


def transcribir(audio_bytes: bytes) -> str:
    segmentos, _ = _whisper().transcribe(io.BytesIO(audio_bytes), language="es")
    return " ".join(s.text.strip() for s in segmentos).strip()


def _limpiar(texto: str) -> str:
    """Quita símbolos de formato para que no se lean en voz alta."""
    texto = re.sub(r"[*_#`•|]", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:900]


def sintetizar(texto: str) -> bytes:
    import edge_tts

    async def _generar():
        datos = b""
        async for trozo in edge_tts.Communicate(_limpiar(texto), VOZ).stream():
            if trozo["type"] == "audio":
                datos += trozo["data"]
        return datos

    return asyncio.run(_generar())
