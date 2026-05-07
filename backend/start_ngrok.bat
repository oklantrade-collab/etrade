@echo off
TITLE Ngrok - Exponer API eTrader
COLOR 0B

echo ============================================================
echo    Iniciando Ngrok para exponer la API (Puerto 8080)
echo ============================================================
echo.

:: Opcional: Verificar si el puerto está en uso
netstat -ano | findstr :8080 >nul
if %errorlevel% neq 0 (
    echo [ADVERTENCIA] No parece haber nada corriendo en el puerto 8080.
    echo Asegurate de que tu API este encendida.
    echo.
)

ngrok http 8080

echo.
echo ============================================================
echo Ngrok se ha detenido. 
pause