#!/usr/bin/env bash
# Arranque automático de proyectoC3 al encender la Raspberry Pi (sin internet).
#
#   sudo bash scripts/instalar_servicio.sh               # instalar y arrancar
#   sudo bash scripts/instalar_servicio.sh --desinstalar # quitar el arranque automático
#
# Crea /etc/systemd/system/proyectoc3.service con las rutas de ESTA carpeta y tu
# usuario. No depende de la red: arranca aunque no haya Wi-Fi ni cable.
set -euo pipefail

SERVICIO=proyectoc3
UNIT="/etc/systemd/system/${SERVICIO}.service"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
USUARIO="${SUDO_USER:-}"

info()  { echo -e "\033[1;32m[ok]\033[0m $*"; }
aviso() { echo -e "\033[1;33m[aviso]\033[0m $*"; }
error() { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "Ejecuta con sudo: sudo bash $0"

if [[ "${1:-}" == "--desinstalar" ]]; then
  systemctl disable --now "$SERVICIO" 2>/dev/null || true
  rm -f "$UNIT"
  systemctl daemon-reload
  info "Arranque automático quitado."
  exit 0
fi

[[ -n "$USUARIO" && "$USUARIO" != "root" ]] || error "Ejecútalo con sudo desde tu usuario (no como root directo)"
PY="$RAIZ/device/.venv/bin/python"
[[ -x "$PY" ]] || error "No existe $PY. Crea el entorno: python3 -m venv device/.venv && device/.venv/bin/pip install -r device/requirements.txt"
[[ -f "$RAIZ/.env" ]] || error "No existe $RAIZ/.env (cp .env.example .env)"

# Carpeta de datos privados (rostros, modelo, base de datos), según el .env
DATA_DIR="$(grep -E '^PROYECTO_C3_DATA=' "$RAIZ/.env" | tail -1 | cut -d= -f2- || true)"
DATA_DIR="${DATA_DIR:-$RAIZ/data}"
sudo -u "$USUARIO" mkdir -p "$DATA_DIR"

# ¿Hay un `serve` corriendo a mano? Chocaría con el servicio (puerto y cámara).
if pgrep -u "$USUARIO" -f "device.cli (serve|tft)" >/dev/null; then
  aviso "Hay un 'device.cli serve' o 'tft' abierto a mano: lo detengo para que el servicio use la cámara."
  pkill -u "$USUARIO" -f "device.cli (serve|tft)" || true
  sleep 2
fi

cat >"$UNIT" <<EOF
[Unit]
Description=proyectoC3 - control de acceso facial (API, panel web y pantalla TFT)
# Sin dependencia de red: funciona sin internet.
After=local-fs.target systemd-udevd.service

[Service]
Type=simple
User=$USUARIO
SupplementaryGroups=video input
WorkingDirectory=$RAIZ
EnvironmentFile=$RAIZ/.env
Environment=PYTHONUNBUFFERED=1
# Oculta el cursor de la consola de texto para que no parpadee sobre la pantalla
ExecStartPre=+/bin/sh -c 'echo 0 > /sys/class/graphics/fbcon/cursor_blink 2>/dev/null || true'
ExecStart=$PY -m device.cli serve
Restart=always
RestartSec=5
# Endurecimiento
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=read-only
ReadWritePaths=$DATA_DIR $RAIZ

[Install]
WantedBy=multi-user.target
EOF
info "Servicio creado: $UNIT"

systemctl daemon-reload
systemctl enable "$SERVICIO" >/dev/null 2>&1
systemctl restart "$SERVICIO"
sleep 4
if systemctl is-active --quiet "$SERVICIO"; then
  info "Servicio activo y habilitado para arrancar al encender."
else
  aviso "El servicio no quedó activo. Revisa: journalctl -u $SERVICIO -n 50"
fi
journalctl -u "$SERVICIO" -n 8 --no-pager || true

cat <<EOF

Comandos útiles:
  Ver estado:      systemctl status $SERVICIO
  Ver mensajes:    journalctl -u $SERVICIO -f
  Reiniciar:       sudo systemctl restart $SERVICIO
  Detener (p. ej. antes de tft-calibrar o tft-test):  sudo systemctl stop $SERVICIO
  Quitar arranque automático: sudo bash $0 --desinstalar
EOF
