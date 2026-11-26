#!/usr/bin/env bash
# Diagnóstico de la pantalla TFT 3.5" (ILI9486 + XPT2046).
#   sudo bash scripts/diagnostico_pantalla_tft.sh
# Copia TODA la salida y compártela si la pantalla no funciona.
set -u
BOOT=/boot/firmware
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sec() { echo; echo "===== $*"; }

[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo: sudo bash $0"; exit 1; }

sec "Sistema"
tr -d '\0' </proc/device-tree/model; echo
uname -r
grep PRETTY_NAME /etc/os-release
echo "rama git: $(git -C "$RAIZ" branch --show-current 2>/dev/null)"

sec "config.txt (líneas activas relacionadas)"
grep -n -E '^[^#]*(dtoverlay|dtparam=spi|display_auto|max_framebuffers|^\[)' "$BOOT/config.txt"

sec "Archivos de overlay"
ls -l "$BOOT/overlays/tft35a.dtbo" "$BOOT/overlays/piscreen.dtbo" 2>&1

sec "¿El overlay se aplicó? (nodos en el árbol de dispositivos)"
NODOS="$(find /proc/device-tree -name 'tft35a*' -o -name 'piscreen*' 2>/dev/null)"
echo "${NODOS:-NINGUNO}"
for n in $NODOS; do
  [[ -f "$n/status" ]] && echo "  $n status=$(tr -d '\0' <"$n/status")"
done

sec "Dispositivos SPI y su driver"
for d in /sys/bus/spi/devices/*; do
  [[ -e "$d" ]] || { echo "NINGUNO (¿SPI desactivado?)"; break; }
  drv="$(readlink "$d/driver" 2>/dev/null)"; drv="${drv##*/}"
  echo "$(basename "$d"): $(cat "$d/modalias" 2>/dev/null) -> driver: ${drv:-SIN DRIVER}"
done

sec "Módulos cargados"
lsmod | grep -E 'fbtft|fb_ili9486|ili9486|ads7846|mipi_dbi' || echo "ninguno relevante"

sec "Framebuffers"
for f in /sys/class/graphics/fb*; do
  [[ -e "$f/name" ]] && echo "$(basename "$f"): $(cat "$f/name") $(cat "$f/virtual_size" 2>/dev/null) $(cat "$f/bits_per_pixel" 2>/dev/null)bpp"
done
ls -l /dev/fb* 2>&1

sec "Táctil"
grep -B1 -A4 -i 'ads7846' /proc/bus/input/devices || echo "NO detectado"

sec "Mensajes del kernel"
dmesg | grep -i -E 'fbtft|ili9486|ads7846|spi0|spi-dw|tft35a|piscreen|graphics fb|dtoverlay' | tail -40

sec "Mensajes del firmware (carga de overlays)"
if command -v vclog >/dev/null; then
  vclog --msg 2>/dev/null | grep -i -E 'overlay|tft35a|piscreen|failed|error' | tail -20
else
  echo "vclog no disponible"
fi

sec "Proyecto"
U="${SUDO_USER:-}"
[[ -n "$U" ]] && echo "grupos de $U: $(id -nG "$U")"
grep -E '^TFT_' "$RAIZ/.env" 2>/dev/null || echo "sin variables TFT_ en .env"
[[ -x "$RAIZ/device/.venv/bin/python" ]] && echo "venv: ok" || echo "venv: NO existe device/.venv"
systemctl is-active proyectoc3 2>/dev/null | sed 's/^/servicio proyectoc3: /'

sec "VEREDICTO"
FB_TFT="$(grep -l -i ili9486 /sys/class/graphics/fb*/name 2>/dev/null | head -1)"
if [[ -n "$FB_TFT" ]]; then
  FB="/dev/$(basename "$(dirname "$FB_TFT")")"
  echo "El driver de la pantalla CARGÓ en $FB."
  echo "Si se ve blanca, la pantalla no aceptó la secuencia de inicio: prueba el otro perfil:"
  echo "  sudo PERFIL=piscreen bash scripts/instalar_pantalla_tft.sh && sudo reboot"
  echo "Para probar: device/.venv/bin/python -m device.cli tft-test"
elif [[ -n "$NODOS" ]]; then
  echo "El overlay se aplicó pero el driver NO creó la pantalla: revisa 'Mensajes del kernel'."
  echo "Prueba el perfil oficial: sudo PERFIL=piscreen bash scripts/instalar_pantalla_tft.sh && sudo reboot"
elif ! grep -q -E '^[^#]*dtoverlay=(tft35a|piscreen)' "$BOOT/config.txt"; then
  echo "config.txt NO tiene la línea de la pantalla: ejecuta sudo bash scripts/instalar_pantalla_tft.sh"
else
  echo "config.txt tiene la línea pero el firmware NO aplicó el overlay."
  echo "Revisa 'Mensajes del firmware' y prueba: sudo PERFIL=piscreen bash scripts/instalar_pantalla_tft.sh && sudo reboot"
fi
