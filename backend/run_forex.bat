@echo off
title eTrade - Forex Management Bot
cd /d c:\Fuentes\eTrade\backend
echo [INFO] Iniciando el servicio de Forex Standalone...
echo [INFO] Usando PM2 para garantizar persistencia...

:: Verificar si PM2 está instalado
where pm2 >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] PM2 no encontrado. Iniciando con Python directo...
    python -m app.workers.forex_worker_standalone
) else (
    :: Detener si ya existe, y arrancar de nuevo
    pm2 stop etrade-forex 2>nul
    pm2 delete etrade-forex 2>nul
    pm2 start app/workers/forex_worker_standalone.py --name etrade-forex --interpreter python
    echo [OK] Forex Worker iniciado en PM2 (nombre: etrade-forex)
    pm2 save
    pm2 list
)
pause
