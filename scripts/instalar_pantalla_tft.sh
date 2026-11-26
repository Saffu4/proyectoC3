#!/usr/bin/env bash
# Instala la pantalla TFT 3.5" SPI (ILI9486 + táctil XPT2046) en la Raspberry Pi 5.
#
#   sudo bash scripts/instalar_pantalla_tft.sh              # instalar (horizontal, rotate=90)
#   sudo ROTACION=270 bash scripts/instalar_pantalla_tft.sh # horizontal invertida
#   sudo bash scripts/instalar_pantalla_tft.sh --desinstalar
#
# Perfiles de driver (PERFIL=...), todos para la misma pantalla y pines:
#   tft35a        (por defecto) overlay del fabricante (LCD-show), compilado aquí
#   piscreen      overlay OFICIAL de Raspberry Pi (ya viene en el sistema), fbtft
#   piscreen-drm  overlay oficial con el driver moderno DRM/KMS
# Si la pantalla queda en blanco con uno, prueba el siguiente:
#   sudo PERFIL=piscreen bash scripts/instalar_pantalla_tft.sh && sudo reboot
#
# Qué hace (todo reversible):
#   1. Instala device-tree-compiler y compila hardware/tft35a/tft35a-overlay.dts
#      en /boot/firmware/overlays/tft35a.dtbo
#   2. Respalda config.txt y añade un bloque marcado con dtparam=spi=on y
#      dtoverlay=tft35a (NO desactiva vc4-kms-v3d: el HDMI sigue funcionando)
#   3. Añade tu usuario a los grupos video (pantalla) e input (táctil)
#   4. Activa TFT_ENABLED=true en el .env del proyecto
# No reinicia: te dice cuándo hacerlo.
set -euo pipefail

ROTACION="${ROTACION:-90}"
PERFIL="${PERFIL:-tft35a}"
VELOCIDAD="${VELOCIDAD:-16000000}"
BOOT_DIR="${BOOT_DIR:-/boot/firmware}"   # sobrescribible solo para pruebas
CONFIG="$BOOT_DIR/config.txt"
OVERLAY_DST="$BOOT_DIR/overlays/tft35a.dtbo"
MARCA_INI="# >>> proyectoC3 pantalla TFT 3.5 (no editar este bloque a mano)"
MARCA_FIN="# <<< proyectoC3 pantalla TFT 3.5"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DTS="$RAIZ/hardware/tft35a/tft35a-overlay.dts"
ENV_FILE="$RAIZ/.env"
USUARIO="${SUDO_USER:-$(logname 2>/dev/null || echo "")}"

info()  { echo -e "\033[1;32m[ok]\033[0m $*"; }
aviso() { echo -e "\033[1;33m[aviso]\033[0m $*"; }
error() { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || error "Ejecuta con sudo: sudo bash $0"
[[ -f "$CONFIG" ]] || error "No existe $CONFIG (¿es Raspberry Pi OS Bookworm/Trixie?)"
case "$ROTACION" in 0|90|180|270) ;; *) error "ROTACION debe ser 0, 90, 180 o 270";; esac
case "$PERFIL" in tft35a|piscreen|piscreen-drm) ;; *) error "PERFIL debe ser tft35a, piscreen o piscreen-drm";; esac

quitar_bloque() {
  # borra el bloque marcado (si existe) sin tocar nada más
  sed -i "/^${MARCA_INI//\//\\/}\$/,/^${MARCA_FIN//\//\\/}\$/d" "$CONFIG"
}

if [[ "${1:-}" == "--desinstalar" ]]; then
  cp -a "$CONFIG" "$CONFIG.bak-proyectoc3-$(date +%Y%m%d-%H%M%S)"
  quitar_bloque
  rm -f "$OVERLAY_DST"
  if [[ -f "$ENV_FILE" ]]; then sed -i 's/^TFT_ENABLED=.*/TFT_ENABLED=false/' "$ENV_FILE"; fi
  info "Pantalla TFT desinstalada. Reinicia: sudo reboot"
  exit 0
fi

MODELO="$(tr -d '\0' </proc/device-tree/model 2>/dev/null || echo desconocido)"
info "Placa: $MODELO"
[[ "$MODELO" == *"Raspberry Pi"* ]] || aviso "No parece una Raspberry Pi; continúo de todos modos"

# 1. Overlay ---------------------------------------------------------------------
info "Perfil de driver: $PERFIL"
if [[ "$PERFIL" == "tft35a" ]]; then
  [[ -f "$DTS" ]] || error "No encuentro $DTS"
  if ! command -v dtc >/dev/null; then
    info "Instalando device-tree-compiler…"
    apt-get update -qq && apt-get install -y -qq device-tree-compiler
  fi
  dtc -@ -q -I dts -O dtb -o "$OVERLAY_DST" "$DTS"
  info "Overlay compilado en $OVERLAY_DST"
  LINEA="dtoverlay=tft35a,rotate=${ROTACION},speed=${VELOCIDAD}"
  CAL="3936,227,268,3880,1"
else
  [[ -f "$BOOT_DIR/overlays/piscreen.dtbo" ]] || error "Este sistema no trae piscreen.dtbo; actualiza: sudo apt update && sudo apt full-upgrade"
  LINEA="dtoverlay=piscreen,rotate=${ROTACION},speed=${VELOCIDAD}"
  [[ "$PERFIL" == "piscreen-drm" ]] && LINEA="${LINEA},drm"
  CAL="3936,227,268,3880,0"   # piscreen ya intercambia los ejes del táctil en el driver
fi

# 2. config.txt -----------------------------------------------------------------
RESPALDO="$CONFIG.bak-proyectoc3-$(date +%Y%m%d-%H%M%S)"
cp -a "$CONFIG" "$RESPALDO"
info "Respaldo de config.txt: $RESPALDO"

# Desactivar overlays de pantallas SPI anteriores (LCD-show, fbtft genérico…)
# que chocarían con este en el mismo bus SPI.
for viejo in tft35a waveshare35a mhs35 fbtft ads7846 piscreen; do
  if grep -Eq "^[[:space:]]*dtoverlay=${viejo}([,:]|$)" "$CONFIG"; then
    sed -i -E "s/^([[:space:]]*dtoverlay=${viejo}([,:].*)?)$/#\1  # desactivado por proyectoC3/" "$CONFIG"
    aviso "Comentada una línea dtoverlay=${viejo} previa"
  fi
done
quitar_bloque
{
  echo ""
  echo "$MARCA_INI"
  echo "[all]"
  echo "dtparam=spi=on"
  echo "$LINEA"
  echo "$MARCA_FIN"
} >>"$CONFIG"
info "config.txt: dtparam=spi=on + $LINEA"

# 3. Permisos -------------------------------------------------------------------
if [[ -n "$USUARIO" && "$USUARIO" != "root" ]]; then
  usermod -aG video,input "$USUARIO"
  info "Usuario $USUARIO añadido a los grupos video e input"
else
  aviso "No pude saber tu usuario: añádelo a mano con 'sudo usermod -aG video,input TU_USUARIO'"
fi

# 4. .env del proyecto ----------------------------------------------------------
if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^TFT_ENABLED=' "$ENV_FILE"; then
    sed -i 's/^TFT_ENABLED=.*/TFT_ENABLED=true/' "$ENV_FILE"
  else
    printf '\n# Pantalla TFT 3.5 (docs/pantalla-tft.md)\nTFT_ENABLED=true\n' >>"$ENV_FILE"
  fi
  if grep -q '^TFT_TOUCH_CAL=' "$ENV_FILE"; then
    sed -i "s/^TFT_TOUCH_CAL=.*/TFT_TOUCH_CAL=${CAL}/" "$ENV_FILE"
  else
    echo "TFT_TOUCH_CAL=${CAL}" >>"$ENV_FILE"
  fi
  info "TFT_ENABLED=true en $ENV_FILE"
else
  aviso "No hay $ENV_FILE: copia .env.example a .env y pon TFT_ENABLED=true"
fi

cat <<EOF

Listo. Ahora:
  1) sudo reboot
  2) Comprueba la pantalla y el táctil (barras de color; si queda blanca, ejecuta
     sudo bash scripts/diagnostico_pantalla_tft.sh):
       cd $RAIZ && device/.venv/bin/python -m device.cli tft-test
  3) Si el servicio corre con systemd, añade en [Service]:
       SupplementaryGroups=video input
     y reinícialo: sudo systemctl daemon-reload && sudo systemctl restart proyectoc3
Para deshacer todo: sudo bash $0 --desinstalar
EOF
