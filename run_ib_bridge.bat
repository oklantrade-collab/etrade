@echo off
set "PROJECT_DIR=%~dp0"
IF NOT EXIST "%PROJECT_DIR%backend\app" IF EXIST "C:\Fuentes\etrade\backend\app" set "PROJECT_DIR=C:\Fuentes\etrade\"
IF NOT EXIST "%PROJECT_DIR%backend\app" IF EXIST "D:\Fuentes\etrade\backend\app" set "PROJECT_DIR=D:\Fuentes\etrade\"
IF NOT EXIST "%PROJECT_DIR%backend\app" (
    echo [ERROR] No se encontro la carpeta del proyecto. Edita PROJECT_DIR en este .bat.
    pause
    exit /b 1
)
cd /d "%PROJECT_DIR%"
set PYTHONPATH=%cd%
TITLE eTrade Interactive Brokers Bridge
cd /d "%PROJECT_DIR%backend"
set PYTHONPATH=%cd%;%PYTHONPATH%
echo ========================================================
echo    eTrade Stocks - Interactive Brokers Paper Bridge
echo    Modalidad: PAPER TRADING  ^|  Puerto: 7497
echo ========================================================
echo.
echo [1/3] Verificando entorno Python...
IF EXIST "..\.venv\Scripts\python.exe" (
    SET PYTHON_EXE=..\.venv\Scripts\python.exe
) ELSE IF EXIST ".\venv\Scripts\python.exe" (
    SET PYTHON_EXE=.\venv\Scripts\python.exe
) ELSE (
    SET PYTHON_EXE=python
)

%PYTHON_EXE% -c "import ibapi" >nul 2>&1
IF ERRORLEVEL 1 (
    echo       ibapi no encontrado. Instalando...
    %PYTHON_EXE% -m pip install ibapi
) ELSE (
    echo       [OK] ibapi disponible.
)

echo [2/3] Verificando que TWS escuche en 127.0.0.1:7497...
%PYTHON_EXE% -c "import socket,sys;s=socket.socket();s.settimeout(3);sys.exit(0 if s.connect_ex(('127.0.0.1',7497))==0 else 1)"
IF ERRORLEVEL 1 (
    echo       [AVISO] Puerto 7497 cerrado. Abre TWS en modo PAPER y activa la API.
    echo       El bridge reintentara automaticamente cada 15s.
)

echo [3/3] Iniciando IB Bridge Worker...
echo.

:run_bridge
%PYTHON_EXE% -m app.workers.ib_bridge_worker
echo [AVISO] El bridge se detuvo. Reiniciando en 3 segundos...
timeout /t 3 /nobreak >nul
goto run_bridge
