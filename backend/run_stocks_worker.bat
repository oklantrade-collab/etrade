@echo off
TITLE eTrade Stocks Scheduler
set "BACKEND_DIR=%~dp0"
IF NOT EXIST "%BACKEND_DIR%app" IF EXIST "C:\Fuentes\etrade\backend\app" set "BACKEND_DIR=C:\Fuentes\etrade\backend\"
IF NOT EXIST "%BACKEND_DIR%app" IF EXIST "D:\Fuentes\etrade\backend\app" set "BACKEND_DIR=D:\Fuentes\etrade\backend\"
cd /d "%BACKEND_DIR%"
set PYTHONPATH=%cd%;%PYTHONPATH%

IF EXIST "..\.venv\Scripts\python.exe" (
    SET PYTHON_EXE=..\.venv\Scripts\python.exe
) ELSE IF EXIST ".\venv\Scripts\python.exe" (
    SET PYTHON_EXE=.\venv\Scripts\python.exe
) ELSE (
    SET PYTHON_EXE=python
)

echo ========================================================
echo    eTrade Stocks Scheduler (%BACKEND_DIR%)
echo ========================================================
:run_stocks
%PYTHON_EXE% -m app.workers.stocks_scheduler
echo [AVISO] El Stocks Scheduler se detuvo. Reiniciando en 5 segundos...
timeout /t 5 /nobreak >nul
goto run_stocks
