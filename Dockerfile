# Debian 13 (trixie) retiró openjdk-17 de sus repositorios y solo ofrece el 21.
# Spark 3.5 admite Java 8/11/17, no 21 (ese llegó con Spark 4), así que la base
# se ancla a Debian 12 (bookworm) en lugar de seguir la etiqueta móvil.
FROM python:3.12-slim-bookworm
# Java para PySpark
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
    && rm -rf /var/lib/apt/lists/*
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Voz del agente, en capa propia: tocarla no obliga a reinstalar todo lo anterior.
COPY requirements-voz.txt .
RUN pip install --no-cache-dir -r requirements-voz.txt
# El modelo de Whisper se descarga al construir la imagen, no la primera vez que alguien usa el
# micrófono: en Azure Container Apps esa descarga en caliente fallaba o agotaba la espera.
ENV WHISPER_DIR=/opt/whisper
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('small', device='cpu', compute_type='int8', download_root='/opt/whisper')" \
    || echo "AVISO: no se pudo precargar el modelo de voz; se descargará al usar el micrófono"
# Lectura OCR. torch desde el índice de CPU de PyTorch: la rueda de PyPI para
# Linux trae CUDA (>2 GB) y aquí no hay GPU que la aproveche.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch torchvision
COPY requirements-ocr.txt .
RUN pip install --no-cache-dir -r requirements-ocr.txt
COPY . .
EXPOSE 8501 8000
