@echo off
chcp 65001 >nul
cd /d "%~dp0\.."
echo === Subir el visor de clorofila-a a tu servidor de Oracle Cloud ===
echo.
set /p IP=IP publica del servidor (ej. 129.153.10.20): 
set /p LLAVE=Arrastra aqui el archivo de la llave privada (.key) y pulsa Enter: 
set LLAVE=%LLAVE:"=%
icacls "%LLAVE%" /inheritance:r /grant:r "%USERNAME%:R" >nul
echo.
echo Empaquetando la app y tus mapas (sin .venv)...
powershell -NoProfile -Command "$f=Get-ChildItem -Force | Where-Object { $_.Name -notin @('.venv','__pycache__') }; Compress-Archive -Path $f.FullName -DestinationPath \"$env:TEMP\app_clorofila_nube.zip\" -Force"
echo Subiendo (puede tardar unos minutos)...
scp -i "%LLAVE%" -o StrictHostKeyChecking=accept-new "%TEMP%\app_clorofila_nube.zip" ubuntu@%IP%:~/
if errorlevel 1 (
  echo No se pudo subir. Revisa la IP, la llave y que la instancia este encendida.
  pause
  exit /b 1
)
echo Instalando en el servidor (unos 5-10 minutos la primera vez)...
ssh -t -i "%LLAVE%" ubuntu@%IP% "sudo apt-get install -y -qq unzip >/dev/null; mkdir -p app_clorofila && cd app_clorofila && unzip -oq ../app_clorofila_nube.zip && bash nube/instalar_nube.sh"
echo.
echo Abre en el navegador: http://%IP%:8765
pause
