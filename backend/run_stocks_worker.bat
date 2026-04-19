@echo off
TITLE eTrade Stocks Scheduler
cd /d C:\fuentes\etrade\backend
echo [1/2] Matando procesos Python remanentes...
taskkill /F /IM python.exe /T 2>nul
echo [2/2] Iniciando Stocks Scheduler...
.\venv\Scripts\python -m app.workers.stocks_scheduler
pause
