@echo off
TITLE eTrader v2 Launcher
COLOR 0A

echo ============================================================
echo          eTrader v2 - INICIANDO ENTORNO COMPLETO
echo ============================================================
echo.

:: 1. Iniciar Frontend en una nueva ventana (Puerto 3000)
echo [1/4] Iniciando UI (Frontend) en ventana decorada...
start "eTrader-Frontend" /D "C:\Fuentes\eTrade\frontend" cmd /k "npm run dev"

:: 2. Iniciar Backend API (Puerto 8080) - NECESARIO PARA DIAGNOSTICO
echo [2/4] Iniciando API (Port 8080) en ventana decorada...
start "eTrader-API" /D "C:\Fuentes\eTrade\backend" cmd /k "..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8080"

:: 3. Iniciar Bot Programador (cada 15 min) en una nueva ventana
echo [3/4] Iniciando Bot Programador (Ciclo 15 min)...
start "eTrader-Bot-Scheduler" /D "C:\Fuentes\eTrade\backend" cmd /k "..\.venv\Scripts\python.exe run_bot.py"

:: 4. Ejecutar el Trabajador Manual en la ventana actual
echo [4/4] Ejecutando Primer Ciclo de Trading (Manual)...
echo.
cd /d "C:\Fuentes\eTrade\backend"
..\.venv\Scripts\python.exe -m app.workers.unified_trading_worker

echo.
echo ============================================================
echo  LISTO: Frontend, API y Bot estan corriendo.
echo  Esta ventana mostrara los logs de la ejecucion manual.
echo ============================================================
pause
