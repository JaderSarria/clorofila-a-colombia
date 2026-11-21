@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Primero ejecuta instalar.bat
  pause
  exit /b 1
)
.venv\Scripts\python -m pip install -q -r requirements.txt
echo Abriendo el visor en el navegador... (no cierres esta ventana mientras lo uses)
.venv\Scripts\python servidor.py
pause
