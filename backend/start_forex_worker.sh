#!/bin/bash
# start_forex_worker.sh
# Iniciar el Forex Worker en el servidor

cd /path/to/etrade/backend
source .env

echo "Iniciando Forex Worker..."
echo "Servidor: $CTRADER_ENV"
echo "Cuenta: $CTRADER_ACCOUNT_ID"

# Activar entorno virtual
source venv/bin/activate

# Correr el worker
python app/workers/forex_worker_standalone.py \
  >> logs/forex_worker.log 2>&1 &

PID=$!
echo "Worker iniciado PID: $PID"
echo $PID > logs/forex_worker.pid
echo "Logs: tail -f logs/forex_worker.log"
