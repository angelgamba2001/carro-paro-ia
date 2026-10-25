"""
Voz del agente (opcional): audio -> texto con Whisper local y texto -> audio con edge-tts.
    pip install -r requirements-voz.txt
Whisper corre en el equipo (el audio no sale). edge-tts envía SOLO el texto de la respuesta
al servicio de voz de Microsoft; para voz 100 % local se puede reemplazar por pyttsx3.
"""
import asyncio
import importlib.util
import io
import re
import wave
from functools import lru_cache
from math import gcd

import numpy as np

VOZ = "es-CO-SalomeNeural"      # alternativa masculina: es-CO-GonzaloNeural
MODELO_WHISPER = "small"        # "base" es más liviano; "medium" más preciso
FRECUENCIA_WHISPER = 16000      # Whisper trabaja siempre a 16 kHz mono


def voz_disponible() -> bool:
    return all(importlib.util.find_spec(m) for m in ("faster_whisper", "edge_tts"))


@lru_cache(maxsize=1)
def _whisper():
    from faster_whisper import WhisperModel
    return WhisperModel(MODELO_WHISPER, device="cpu", compute_type="int8")


def _wav_a_muestras(audio_bytes: bytes) -> np.ndarray:
    """WAV -> muestras float32, mono, 16 kHz.

    Se decodifica aquí en vez de dejárselo a faster-whisper porque este delega en
    PyAV y llama a av.open(..., metadata_errors=...), parámetro que las versiones
    recientes de PyAV ya no aceptan: TypeError al transcribir. La biblioteca
    estándar lee el WAV de st.audio_input sin depender de esa versión.
    """
    with wave.open(io.BytesIO(audio_bytes), "rb") as w:
        canales = w.getnchannels()
        ancho = w.getsampwidth()
        frecuencia = w.getframerate()
        crudo = w.readframes(w.getnframes())

    tipos = {1: np.uint8, 2: np.int16, 4: np.int32}
    if ancho not in tipos:
        raise ValueError(f"Ancho de muestra no soportado: {ancho} bytes")

    datos = np.frombuffer(crudo, dtype=tipos[ancho]).astype(np.float32)
    if ancho == 1:                      # el PCM de 8 bits es sin signo, centrado en 128
        datos = (datos - 128.0) / 128.0
    else:
        datos /= float(2 ** (8 * ancho - 1))

    if canales > 1:                     # mezcla a mono promediando los canales
        datos = datos.reshape(-1, canales).mean(axis=1)

    if frecuencia != FRECUENCIA_WHISPER:
        from scipy.signal import resample_poly
        divisor = gcd(int(frecuencia), FRECUENCIA_WHISPER)
        datos = resample_poly(datos, FRECUENCIA_WHISPER // divisor, int(frecuencia) // divisor)

    return np.ascontiguousarray(datos, dtype=np.float32)


def transcribir(audio_bytes: bytes) -> str:
    try:
        entrada = _wav_a_muestras(audio_bytes)
    except Exception:
        # No era un WAV legible por la biblioteca estándar (por ejemplo WAVE_FORMAT_EXTENSIBLE
        # o un contenedor distinto): se deja que faster-whisper lo intente por su cuenta.
        entrada = io.BytesIO(audio_bytes)
    segmentos, _ = _whisper().transcribe(entrada, language="es")
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
