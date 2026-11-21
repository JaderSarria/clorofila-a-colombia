@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Zonas disponibles:
.venv\Scripts\python lote.py --lista
echo.
set /p ZONA=Escribe la zona (ej. cienaga_grande): 
set /p DESDE=Desde (AAAA-MM-DD): 
set /p HASTA=Hasta (AAAA-MM-DD): 
.venv\Scripts\python lote.py --zona %ZONA% --desde %DESDE% --hasta %HASTA%
pause
