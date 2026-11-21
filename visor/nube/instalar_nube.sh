#!/usr/bin/env bash
# Instala el visor de clorofila-a en un servidor Ubuntu 24.04 (Oracle Cloud, ARM o x86).
# Uso (en el servidor, dentro de la carpeta app_clorofila):   bash nube/instalar_nube.sh
set -euo pipefail
APP="$(cd "$(dirname "$0")/.." && pwd)"
USUARIO_SO="$(whoami)"
PUERTO=8765
echo "== Instalando el visor de clorofila-a en $APP"

# 1. paquetes del sistema
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv python3-pip unzip curl iptables-persistent
PY=python3
PYV=$(python3 -c 'import sys;print(sys.version_info[1])')
if [ "$PYV" -lt 11 ]; then
  echo "Python 3.$PYV es antiguo: instalando Python 3.12…"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y software-properties-common
  sudo add-apt-repository -y ppa:deadsnakes/ppa && sudo apt-get update -y
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3.12 python3.12-venv
  PY=python3.12
fi

# 2. entorno de Python
cd "$APP"
$PY -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -c "import joblib; joblib.load('modelo/modelo_clorofila.joblib'); print('Modelo cargado correctamente')"

# 3. usuario y contraseña del visor
if [ ! -f "$HOME/.clorofila.env" ]; then
  read -rp "Usuario para entrar al visor [redcam]: " U; U=${U:-redcam}
  while true; do
    read -rsp "Contraseña para entrar al visor (mín. 8 caracteres): " C; echo
    [ ${#C} -ge 8 ] && break; echo "Muy corta."
  done
  printf 'CLOROFILA_HOST=0.0.0.0\nCLOROFILA_USUARIO=%s\nCLOROFILA_CLAVE=%s\n' "$U" "$C" > "$HOME/.clorofila.env"
  chmod 600 "$HOME/.clorofila.env"
fi

# 4. servicio del visor (arranca solo y se reinicia si falla)
sudo tee /etc/systemd/system/clorofila.service >/dev/null <<EOF
[Unit]
Description=Visor de clorofila-a
After=network-online.target
Wants=network-online.target
[Service]
User=$USUARIO_SO
WorkingDirectory=$APP
EnvironmentFile=$HOME/.clorofila.env
ExecStart=$APP/.venv/bin/python servidor.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

# 5. procesamiento automático cada noche (2:00 a. m. hora Colombia = 07:00 UTC)
sudo tee /etc/systemd/system/clorofila-noche.service >/dev/null <<EOF
[Unit]
Description=Clorofila-a: calcula las imágenes nuevas de las zonas
[Service]
Type=oneshot
User=$USUARIO_SO
WorkingDirectory=$APP
ExecStart=$APP/.venv/bin/python lote_auto.py
StandardOutput=append:$APP/automatico.log
StandardError=append:$APP/automatico.log
EOF
sudo tee /etc/systemd/system/clorofila-noche.timer >/dev/null <<EOF
[Unit]
Description=Clorofila-a: cada noche
[Timer]
OnCalendar=*-*-* 07:00:00 UTC
Persistent=true
[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now clorofila.service clorofila-noche.timer

# 6. abrir el puerto en el cortafuegos interno de Ubuntu (Oracle lo trae cerrado)
if ! sudo iptables -C INPUT -m state --state NEW -p tcp --dport $PUERTO -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 1 -m state --state NEW -p tcp --dport $PUERTO -j ACCEPT
  sudo netfilter-persistent save
fi

sleep 4
IP=$(curl -s -4 ifconfig.me || echo "IP_PUBLICA")
echo
echo "=============================================================="
echo " Listo. Abre en el navegador:   http://$IP:$PUERTO"
echo " (si no abre: falta la regla de entrada del puerto $PUERTO en Oracle, paso 6 de la guía)"
echo " Procesamiento automático: cada noche a las 2:00 a. m. (hora Colombia)."
echo " Ver lo que hizo:   tail -n 50 $APP/automatico.log"
echo "=============================================================="
systemctl --no-pager --lines=3 status clorofila.service || true
