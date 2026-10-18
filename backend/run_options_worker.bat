@echo off
TITLE eTrade Options Worker (PAPER - solo lectura)
cd /d C:\fuentes\etrade\backend
REM IMPORTANTE: NO usa taskkill /IM python.exe (mataria el Stocks Worker). Si hay una instancia previa, cierre su ventana.
set OPTIONS_ENABLED=true
set OPTIONS_EXECUTION_MODE=paper
if "%OPT_IB_CLIENT_ID%"=="" set OPT_IB_CLIENT_ID=31
echo Iniciando Options Worker (clientId %OPT_IB_CLIENT_ID%)...
if exist .\venv\Scripts\python.exe (
  .\venv\Scripts\python -m app.options.worker
) else (
  ..\.venv\Scripts\python -m app.options.worker
)
pause
