@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando la app de Clorofila-a REDCAM...
where py >nul 2>nul
if errorlevel 1 (
  echo.
  echo No se encontro Python. Instala Python 3.12 desde https://www.python.org/downloads/
  echo y marca la casilla "Add python.exe to PATH". Luego vuelve a ejecutar este archivo.
  pause
  exit /b 1
)
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Hubo un error instalando paquetes. Copia el mensaje de arriba y envialo.
  pause
  exit /b 1
)
echo.
echo Instalacion terminada. Ahora abre "abrir_app.bat".
pause
