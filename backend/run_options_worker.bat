@echo off
TITLE eTrade Options Worker (PAPER - solo lectura)
set "BACKEND_DIR=%~dp0"
IF NOT EXIST "%BACKEND_DIR%app" set "BACKEND_DIR=D:\Fuentes\etrade\backend\"
IF NOT EXIST "%BACKEND_DIR%app" set "BACKEND_DIR=C:\Fuentes\etrade\backend\"
cd /d "%BACKEND_DIR%"
set PYTHONPATH=%cd%;%PYTHONPATH%

REM IMPORTANTE: NO usa taskkill /IM python.exe (mataria el Stocks Worker). Si hay una instancia previa, cierre su ventana.
set OPTIONS_ENABLED=true
set OPTIONS_EXECUTION_MODE=paper
if "%OPT_IB_CLIENT_ID%"=="" set OPT_IB_CLIENT_ID=31

IF EXIST "..\.venv\Scripts\python.exe" (
    SET PYTHON_EXE=..\.venv\Scripts\python.exe
) ELSE IF EXIST ".\venv\Scripts\python.exe" (
    SET PYTHON_EXE=.\venv\Scripts\python.exe
) ELSE (
    SET PYTHON_EXE=python
)

echo ========================================================
echo    eTrade Options - IB Paper Worker (Client ID: %OPT_IB_CLIENT_ID%)
echo ========================================================
echo Iniciando Options Worker en %BACKEND_DIR%...
%PYTHON_EXE% -m app.options.worker
pause
