#!/bin/bash
PID=$(cat logs/forex_worker.pid 2>/dev/null)
if [ -n "$PID" ]; then
    kill $PID
    rm logs/forex_worker.pid
    echo "Worker detenido (PID: $PID)"
else
    echo "Worker no está corriendo"
fi
