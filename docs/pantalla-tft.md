# Pantalla TFT 3.5" táctil (ILI9486 + XPT2046) en la Raspberry Pi 5

Pantalla SPI de 480×320 que se monta sobre los pines GPIO, vendida como
"3.5inch RPi Display" (LCDwiki MPI3501), "tft35a" o Waveshare 3.5" (A).
Controlador de imagen **ILI9486**, táctil resistivo **XPT2046** (compatible ADS7846).

En el proyecto muestra la **vista de acceso**: cámara en vivo con caja
verde/roja y, al tocar la pantalla, la comprobación real de acceso con una
pantalla verde "Bienvenido/a" o roja "Acceso denegado" + motivo.

> ⚠️ El script `LCD35-show` (LCD-show) **no sirve en la Pi 5 con Debian 13**:
> desactiva el driver gráfico KMS y cambia el sistema a X11. No lo ejecutes.
> Si ya lo ejecutaste, restaura `/boot/firmware/config.txt` antes de seguir.

## Cómo funciona

```
cámara ─► device (Flask + LBPH) ─► hilo tft_display ─► /dev/fbN (driver fbtft)
                                         ▲
                     táctil ADS7846 ─► /dev/input/eventN
```

- `hardware/tft35a/tft35a-overlay.dts`: overlay de la pantalla y el táctil
  (mismas propiedades que el `tft35a-overlay.dtb` oficial de LCD-show, pero en
  código fuente revisable). Se compila en la Pi con `dtc`.
- `device/tft_display.py`: dibuja **directo en el framebuffer**, sin escritorio,
  X11 ni Wayland. Corre como hilo dentro de `device.cli serve` para compartir la
  cámara con la API (V4L2 no admite dos procesos leyendo la misma cámara).
- El HDMI sigue funcionando (no se toca `vc4-kms-v3d`).

## Conexión

Apaga la Pi y encaja la pantalla en los **primeros 26 pines** del conector GPIO
(el pin 1 de la pantalla sobre el pin 1 de la Pi, esquina del lector de SD).
Usa: SPI0 (CE0 pantalla, CE1 táctil), GPIO24 = DC, GPIO25 = RESET,
GPIO17 = interrupción del táctil. Al encender, la luz de fondo se ve blanca
hasta que se instale el driver: es normal.

> Con la pantalla puesta, esos pines quedan ocupados. Si usas un ventilador o
> HAT sobre el GPIO, revisa que no choquen.

## Instalación

En la Pi, desde la carpeta del proyecto (rama con este archivo):

```bash
cd ~/Desktop/proyectoC3
git fetch && git checkout feature/pantalla-tft
sudo bash scripts/instalar_pantalla_tft.sh          # horizontal (rotate=90)
sudo reboot
```

El script (seguro de repetir, y se puede deshacer):

1. Compila el overlay en `/boot/firmware/overlays/tft35a.dtbo`.
2. Guarda un respaldo `config.txt.bak-proyectoc3-FECHA` y añade un bloque marcado:
   ```ini
   # >>> proyectoC3 pantalla TFT 3.5 (no editar este bloque a mano)
   [all]
   dtparam=spi=on
   dtoverlay=tft35a,rotate=90,speed=16000000
   # <<< proyectoC3 pantalla TFT 3.5
   ```
   Si encuentra overlays viejos de pantallas SPI (`waveshare35a`, `tft35a`,
   `fbtft`, `mhs35`, `ads7846`) los comenta para que no choquen.
3. Añade tu usuario a los grupos `video` (pantalla) e `input` (táctil).
4. Pone `TFT_ENABLED=true` en `.env`.

Opciones: `sudo ROTACION=270 bash scripts/instalar_pantalla_tft.sh` (horizontal
invertida; también 0 y 180 en vertical). Para deshacer todo:
`sudo bash scripts/instalar_pantalla_tft.sh --desinstalar` y reinicia.

## Si la pantalla queda en blanco

Blanco = la luz de fondo está encendida pero el driver no inicializó la
pantalla. Ejecuta el diagnóstico; al final dice qué falló y qué probar:

```bash
sudo bash scripts/diagnostico_pantalla_tft.sh
```

Hay tres perfiles de driver para esta misma pantalla. Si uno deja la pantalla
en blanco, instala el siguiente y reinicia:

```bash
sudo PERFIL=piscreen bash scripts/instalar_pantalla_tft.sh && sudo reboot
sudo PERFIL=piscreen-drm bash scripts/instalar_pantalla_tft.sh && sudo reboot
```

| Perfil | Qué usa |
|---|---|
| `tft35a` (por defecto) | overlay del fabricante (LCD-show), compilado en la Pi |
| `piscreen` | overlay **oficial** de Raspberry Pi que ya trae el sistema (mismos pines y chip) |
| `piscreen-drm` | el mismo overlay oficial con el driver moderno DRM/KMS |

Con `piscreen`, si el rojo y el azul salen cambiados pon `TFT_SWAP_RB=true` en `.env`.

## Comprobar

Después de reiniciar:

```bash
ls /dev/fb*                                   # debe aparecer fb0 (HDMI) y fb1 (TFT)
cat /sys/class/graphics/fb*/name              # una debe decir fb_ili9486
grep -A4 ADS7846 /proc/bus/input/devices      # el táctil
device/.venv/bin/python -m device.cli tft-test
```

`tft-test` pinta barras de color durante 60 s y, por cada toque, imprime las
coordenadas y dibuja un círculo donde tocaste. Si el círculo cae lejos del dedo,
ajusta la calibración (abajo). Para la vista de acceso no es crítico: tocar en
**cualquier parte** inicia la verificación.

## Usarla

- **Con el servicio** (recomendado): con `TFT_ENABLED=true`,
  `python -m device.cli serve` muestra la vista en la pantalla además de la API.
- **Solo la pantalla**: `python -m device.cli tft` (no arranques también
  `serve`: la cámara solo admite un proceso).

Con systemd, añade los grupos al servicio (ver `deployment-local.md`):

```ini
[Service]
SupplementaryGroups=video input
```

```bash
sudo systemctl daemon-reload && sudo systemctl restart proyectoc3
journalctl -u proyectoc3 | grep tft      # "[tft] Vista de acceso en /dev/fb1 (480x320)…"
```

## Configuración (`.env`)

| Variable | Por defecto | Qué hace |
|---|---|---|
| `TFT_ENABLED` | `false` | `serve` dibuja en la pantalla |
| `TFT_MODE` | `toque` | `toque`: verificar al tocar · `auto`: verificar al ver un rostro ~1 s (pausa de 2 s entre verificaciones) |
| `TFT_RESULT_SECONDS` | `3` | segundos que se ve la pantalla verde/roja |
| `TFT_FPS` | `8` | cuadros por segundo de la vista (el SPI no da para mucho más) |
| `TFT_LIVE_RECOGNITION` | `true` | caja con nombre/motivo en vivo (solo informativa, no registra) |
| `TFT_FB_DEVICE` | autodetectar | forzar, p. ej. `/dev/fb1` |
| `TFT_TOUCH_DEVICE` | autodetectar | forzar, p. ej. `/dev/input/event4` |
| `TFT_TOUCH_CAL` | `3936,227,268,3880,1` | calibración `xmin,xmax,ymin,ymax,swap` (valor del fabricante para rotate=90) |

Solo la verificación (toque o modo auto) registra eventos en `access_events`,
por el mismo camino que `POST /api/access/check`. La vista en vivo no registra.

## Calibrar el táctil

Con `tft-test`, toca la esquina **superior izquierda** y la **inferior derecha**
y anota los valores "crudo". Con `swap=1` (rotate 90/270), la X de pantalla sale
del segundo número crudo y la Y del primero:

```
TFT_TOUCH_CAL=<crudo2 sup-izq>,<crudo2 inf-der>,<crudo1 sup-izq>,<crudo1 inf-der>,1
```

Con rotate 0/180 usa `swap=0` y el orden normal (`crudo1` = X, `crudo2` = Y).

## Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| Pantalla blanca tras reiniciar | El overlay no cargó: `dmesg \| grep -i -E "fbtft\|ili9486"`, revisa el bloque en `config.txt` y que `tft35a.dtbo` exista en `/boot/firmware/overlays/` |
| `No se encontró la pantalla TFT` | Igual que arriba; o fuerza `TFT_FB_DEVICE=/dev/fb1` |
| `Permission denied` en `/dev/fb1` o `/dev/input/event*` | Falta el grupo: cierra sesión/reinicia tras el script, o `SupplementaryGroups=video input` en systemd |
| Imagen solo en parte de la pantalla o rara | Otro overlay de pantalla activo (`grep dtoverlay /boot/firmware/config.txt`): deja solo el bloque de proyectoC3 |
| Colores rojo/azul cambiados | Añade `,bgr=1` a la línea `dtoverlay=tft35a…` |
| Imagen al revés | Reinstala con otra `ROTACION` (90 ↔ 270) |
| El táctil no responde | `sudo apt install evtest && sudo evtest` → elige "ADS7846" y toca: si no hay eventos, revisa que la pantalla esté bien encajada |
| Cursor de consola parpadeando encima | El servicio lo desactiva si tiene permiso; si no: `echo 0 \| sudo tee /sys/class/graphics/fbcon/cursor_blink` |
| Imagen lenta | Normal en SPI (~8 fps). Puedes probar `VELOCIDAD=24000000` al instalar; si aparece ruido, vuelve a 16000000 |

## Poner a funcionar el programa completo

Desde `~/Desktop/proyectoC3` en la Pi (solo la primera vez los pasos 1-3):

```bash
# 1. Entorno de Python y configuración
python3 -m venv device/.venv && device/.venv/bin/pip install -r device/requirements.txt
cp -n .env.example .env        # edita FLASK_SECRET; TFT_ENABLED=true lo pone el instalador

# 2. Administrador del panel web
device/.venv/bin/python -m device.cli init-admin --password 'UNA_CONTRASEÑA_LARGA'

# 3. Personas: importar la del proyecto base (o registrarlas desde el panel web)
device/.venv/bin/python -m device.cli import-base

# 4. Arrancar (API + panel web + pantalla TFT)
device/.venv/bin/python -m device.cli serve
```

- En la consola debe aparecer `[tft] Vista de acceso en /dev/fb1 (480x320)…`.
  Si dice `Pantalla TFT no disponible`, la pantalla aún no está instalada bien
  (ver la sección de pantalla en blanco).
- El panel web queda en `http://127.0.0.1:5000` en la Pi. Desde él se
  registran personas, se capturan rostros y se **entrena** el modelo. Mientras
  no haya modelo entrenado, la pantalla muestra "Modelo sin entrenar".
- Para que arranque solo al encender la Pi, usa el servicio systemd de
  [deployment-local.md](deployment-local.md) (ya incluye los grupos `video` e `input`).
- No ejecutes a la vez `serve` y `tft` ni el `detector.py` del proyecto base:
  la cámara solo admite un programa.
