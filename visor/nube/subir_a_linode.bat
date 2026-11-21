@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
echo === Subir el visor de clorofila-a a tu servidor Linode (Akamai) ===
echo.
set /p IP=IP publica del servidor (ej. 203.0.113.10): 
echo.
echo Empaquetando la app y tus mapas (sin .venv)...
powershell -NoProfile -Command "$f=Get-ChildItem -Force | Where-Object { $_.Name -notin @('.venv','__pycache__') }; Compress-Archive -Path $f.FullName -DestinationPath \"$env:TEMP\app_clorofila_nube.zip\" -Force"
echo.
echo Subiendo. Te pedira la contrasena de root que pusiste al crear el Linode (no se ve al escribirla).
echo Si pregunta "Are you sure you want to continue connecting", escribe yes y Enter.
scp -o StrictHostKeyChecking=accept-new "%TEMP%\app_clorofila_nube.zip" root@%IP%:~/
if errorlevel 1 (
  echo No se pudo subir. Revisa la IP, la contrasena y que el Linode este encendido.
  pause
  exit /b 1
)
echo.
echo Instalando en el servidor (unos 5-10 minutos). Pedira otra vez la contrasena de root.
ssh -t root@%IP% "apt-get update -qq && apt-get install -y -qq unzip >/dev/null; mkdir -p app_clorofila && cd app_clorofila && unzip -oq ../app_clorofila_nube.zip && bash nube/instalar_nube.sh"
echo.
echo Abre en el navegador: http://%IP%:8765
pause
