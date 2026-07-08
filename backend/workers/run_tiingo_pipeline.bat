@echo off
echo Iniciando Pipeline de Tiingo a BigQuery...

cd C:\Fuentes\eTrade\backend

:: Activar el entorno virtual
call ..\.venv\Scripts\activate

:: Ejecutar el script
python workers\tiingo_bq_pipeline.py

echo Pipeline finalizado.
pause
