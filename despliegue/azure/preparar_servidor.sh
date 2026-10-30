#!/usr/bin/env bash
# Prepara una VM Ubuntu de Azure y levanta SMARTDATA 360 · Carro de Paro con HTTPS.
# Uso (dentro de la carpeta del proyecto en la VM):
#   bash despliegue/azure/preparar_servidor.sh carro-paro-demo.eastus.cloudapp.azure.com
set -euo pipefail
DOMINIO="${1:?Indique el dominio de la VM, p. ej. carro-paro-demo.eastus.cloudapp.azure.com}"
cd "$(dirname "$0")/../.."

echo "==> 1/4 Docker"
if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
fi

echo "==> 2/4 Memoria de intercambio (2 GB): EasyOCR y Whisper son pesados para 4 GB de RAM"
if ! sudo swapon --show | grep -q /swapfile; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

echo "==> 3/4 Archivo .env de producción"
fijar() {  # fijar CLAVE VALOR: reemplaza la línea si existe, si no la agrega
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi
}
if [ ! -f .env ]; then
  cp .env.example .env
  fijar JWT_SECRETO "$(openssl rand -hex 32)"
  fijar CLAVE_CIFRADO "$(openssl rand -base64 32 | tr '+/' '-_')"
  # Clave del MySQL del contenedor. NO cambiarla después del primer arranque:
  # MySQL solo la toma al inicializar el volumen.
  fijar DOCKER_DB_PASSWORD "$(openssl rand -hex 16)"
fi
fijar ENTORNO produccion
fijar MOTOR_BIGDATA pandas        # Spark no cabe en 4 GB junto a todo lo demás
fijar AGENTE_PROVEEDOR reglas     # sin modelo de IA: cero costo
fijar REGISTRO_ABIERTO true       # demostración: registro abierto
fijar MS_REDIRECT_URI "https://$DOMINIO"
fijar DOMINIO "$DOMINIO"
chmod 600 .env

echo "==> 4/4 Construcción y arranque (la primera vez tarda 10-20 min)"
sudo docker compose -f docker-compose.yml -f docker-compose.azure.yml up -d --build

echo
echo "Listo. Abra https://$DOMINIO (el certificado puede tardar 1-2 min la primera vez)."
echo "Ver estado:   sudo docker compose -f docker-compose.yml -f docker-compose.azure.yml ps"
echo "Ver errores:  sudo docker compose -f docker-compose.yml -f docker-compose.azure.yml logs -f --tail 100"
