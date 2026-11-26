# Despliegue local (la Pi funciona 24/7)

## Arranque automático al encender (recomendado)

Desde la carpeta del proyecto en la Pi:

```bash
sudo bash scripts/instalar_servicio.sh
```

Crea y habilita `proyectoc3.service` con las rutas de esa carpeta y tu usuario.
Desde ese momento, al conectar la corriente la Pi arranca el programa sola
(API, panel web y pantalla TFT), **sin internet**: el servicio no espera a la
red y, con `SYNC_ENABLED=false`, nada usa internet. Si se cae, se reinicia en 5 s.
Si la cámara o la pantalla tardan en aparecer al encender, el programa las
espera.

| Acción | Comando |
|---|---|
| Ver estado | `systemctl status proyectoc3` |
| Ver mensajes en vivo | `journalctl -u proyectoc3 -f` |
| Reiniciar (tras cambiar `.env` o `git pull`) | `sudo systemctl restart proyectoc3` |
| Detener (antes de `tft-test`, `tft-calibrar`, `capture`…) | `sudo systemctl stop proyectoc3` |
| Quitar el arranque automático | `sudo bash scripts/instalar_servicio.sh --desinstalar` |

No ejecutes `device.cli serve` a mano mientras el servicio está activo: los dos
pelearían por la cámara y el puerto 5000.

### Hora sin internet

Sin internet la Pi no puede poner la hora en línea. La Raspberry Pi 5 tiene
reloj (RTC), pero **solo conserva la hora apagada si tiene batería** (conector
"BAT" junto al USB-C). Sin batería, tras un corte de luz la hora queda
atrasada hasta que haya internet: eso afecta la hora del historial de accesos
y los permisos con **fecha de vencimiento**. Para un punto de acceso sin
internet, instala la batería y ajusta la hora una vez:

```bash
sudo date -s "2026-11-26 13:50"    # hora local actual
sudo hwclock --systohc              # guardarla en el reloj con batería
```

## systemd a mano (referencia)

`/etc/systemd/system/proyectoc3.service`:

```ini
[Unit]
Description=proyectoC3 - control de acceso facial
After=network-online.target

[Service]
Type=simple
User=saffu1
WorkingDirectory=/home/saffu1/Desktop/proyectoC3
EnvironmentFile=/home/saffu1/Desktop/proyectoC3/.env
ExecStart=/home/saffu1/Desktop/proyectoC3/device/.venv/bin/python -m device.cli serve
Restart=on-failure
RestartSec=5
# Pantalla TFT (docs/pantalla-tft.md): acceso a /dev/fb* y /dev/input/event*
SupplementaryGroups=video input
# endurecimiento
PrivateTmp=true
ProtectHome=read-only
ReadWritePaths=/home/saffu1/.local/share/proyectoC3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now proyectoc3
systemctl status proyectoc3
journalctl -u proyectoc3 -f
```

## Transmisión continua (recomendación alternativa)

El servicio de cámara es un hilo DENTRO del proceso Flask (`device/camera.py`,
fuente única por proceso). Puedes separarlo:

- El reconocimiento en tempo real sigue disponible con
  `python -m device.cli access-check` (una comprobación, para CRON/prueba) o
  deja running `detector.py` del proyecto base para la detección continua.
tu mejor biblioteca: **no ejecutar ambos abriendo la cámara al mismo tiempo
** (V4L2 no admite dos lectores). Si quieres mantener el detector del base
corriendo, desactiva el servicio Flask de cámara (`CAM_SOURCE=none`) y sigue
usando el base para la vista.

## Panel web en modo quiosco

Para una pantalla dedicada en el punto de acceso:

1. Navegador en pantalla completa con `/welcome` como destino del evento.
   El evento de reconocimiento viaja por `/api/kiosk/evaluate` con
   `X-Kiosk-Token` de UN SOLO USO (se rota tras cada evaluación) generado en
   la sesión administrativa.
2. Config. El token activo se administra en la tabla `settings`.

## Apagado/entorno seguro

- Respaldos: `tar -C /home/saffu1/.local/share -czf ~/proyectoC3-$(date +%F).tar.gz proyectoC3`.
- Registro de la señal: revisar `journalctl` y el endpoint `/api/audit-log`.
