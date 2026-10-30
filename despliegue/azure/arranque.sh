#!/bin/sh
# Arranque de los contenedores web y api en Azure Container Apps.
# Uso: sh despliegue/azure/arranque.sh web|api
# Todos los contenedores de la replica comparten localhost: MySQL esta en 127.0.0.1.
set -e
MODO="${1:-web}"

echo "[arranque:$MODO] esperando a MySQL..."
python - <<'PY'
import os, socket, sys, time
host, port = os.getenv("DB_HOST", "127.0.0.1"), int(os.getenv("DB_PORT", "3306"))
for _ in range(180):
    try:
        socket.create_connection((host, port), 3).close()
        sys.exit(0)
    except OSError:
        time.sleep(2)
sys.exit("MySQL no respondio en 6 minutos")
PY

if [ "$MODO" = "api" ]; then
    # Espera a que el contenedor web haya creado la base de datos
    python - <<'PY'
import os, time
import mysql.connector
for _ in range(180):
    try:
        mysql.connector.connect(host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "3306")),
                                user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                                database=os.getenv("DB_NAME", "carro_paro_db")).close()
        break
    except Exception:
        time.sleep(5)
PY
    exec uvicorn api.main:app --host 127.0.0.1 --port 8000 --proxy-headers
fi

# Web: crea la BD solo si esta vacia (reintenta mientras MySQL termina su primer arranque)
n=0
until python scripts/inicializar_bd.py --sin-cambio --solo-si-vacia; do
    n=$((n + 1))
    [ "$n" -ge 10 ] && { echo "[arranque:web] no se pudo inicializar la BD"; exit 1; }
    sleep 10
done
for m in migrar_mfa migrar_consentimientos migrar_correo migrar_registro; do
    python "scripts/$m.py"
done

# Historico y pipeline Big Data en segundo plano: la aplicacion abre sin esperarlos
( { [ -d data/raw/revisiones ] || python scripts/generar_historico.py --anios 5 ; } &&
  { [ -f data/gold/_ultima_ejecucion.json ] || python scripts/ejecutar_pipeline.py ; } ) &

exec streamlit run app/main.py --server.address 127.0.0.1 --server.port 8501
