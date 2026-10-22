# Despliegue local (la Pi funciona 24/7)

## systemd (recomendado)

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
