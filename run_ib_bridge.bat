@echo off
TITLE eTrade Interactive Brokers Bridge
cd /d %~dp0backend
echo ========================================================
echo    eTrade Stocks - Interactive Brokers Paper Bridge
echo    Modalidad: PAPER TRADING ^| Puerto: 7497
echo ========================================================
echo.
echo [1/2] Verificando entorno Python...
IF EXIST "..\.venv\Scripts\python.exe" (
    SET PYTHON_EXE=..\.venv\Scripts\python.exe
) ELSE (
    SET PYTHON_EXE=python
)
echo       Ejecutable: %PYTHON_EXE%

%PYTHON_EXE% -c "import ibapi" 2>nul
IF ERRORLEVEL 1 (
    echo       [Instalando] 'ibapi' no se encontro. Instalando via pip...
    %PYTHON_EXE% -m pip install ibapi
)
%PYTHON_EXE% -c "import ibapi; print('       [OK] ibapi version ' + getattr(ibapi, '__version__', 'instalada') + ' lista.')"
echo.
echo [2/2] Iniciando IB Bridge Worker...
echo       Asegurate de que TWS este abierta en modo PAPER TRADING.
echo.
%PYTHON_EXE% -m app.workers.ib_bridge_worker
pause
