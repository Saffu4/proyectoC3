# Guía de instalación (Raspberry Pi 5, Debian 13 ARM64)

## 0. Requisitos

- Raspberry Pi 5 con Debian GNU/Linux 13 (ARM64)
- Webcam USB reconocida (`ls /dev/video*`)
- Python 3 y `python3-venv`
- (opcional) Node.js ≥ 18 para el panel web

> Verificación del entorno base: `cv2.face.LBPHFaceRecognizer_create()` debe
> estar disponible (proyecto base ya la verificaba; los scripts nuevos
> `raise RuntimeError` si no).

## 1. Obtener el código

```bash
cd ~/Desktop
# git clone <repo> proyectoC3   # si el proyecto aún no está en la Pi
cd proyectoC3
```

## 2. Dependencias del servicio

Debian 13 bloquea `pip install` global → **usar venv en cada etapa**.

```bash
cd device
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`requirements.txt` incluye `opencv-contrib-python` (trae `cv2.face`), `numpy`,
`Flask` y `pytest`. El Haar Cascade incluye **copia local** bajo
`device/assets/` (también usa `/usr/share/opencv4/haarcascades` si existe,
como el base).

## 3. Ubicación de datos privados

Elegir `/opt/proyectoC3-data` o `/home/saffu1/.local/share/proyectoC3`.
Debe estar **fuera de Git** (en `~/Desktop/proyectoC3` no se guardan rostros).

```bash
mkdir -p /home/saffu1/.local/share/proyectoC3
chmod 700 /home/saffu1/.local/share/proyectoC3
```

## 4. Configuración del servicio

```bash
cd ~/Desktop/proyectoC3
cp device/requirements.txt . >/dev/null 2>&1 || true
cp device/../.env.example .env 2>/dev/null || cp .env.example .env
```

Edita tu archivo .env (nunca lo montes en tu repo — se encuentra en `.gitignore`):

```bash
nano .env
```

Variables mínimas:

| Variable | Valor |
|---|---|
| `PROYECTO_C3_DATA` | `/home/saffu1/.local/share/proyectoC3` |
| `FLASK_SECRET` | generado: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | cuenta inicial (≥10 caracteres) |
| `CAMERA_INDEX` | índice de la webcam (`0` normalmente) |
| `CASCADE_PATH` | auto; ajustar si la Pi no tiene `/usr/share/opencv4` |
| `LBPH_THRESHOLD` | inicia en `65.0`; calibrar (ver authorization-guide) |

## 5. Migrar el proyecto base (paso único)

El base tenía UNA persona autorizada (etiqueta 1). Este comando la integra:

```bash
cd ~/Desktop/proyectoC3
device/.venv/bin/python -m device.cli import-base \
  --src ~/Desktop/rostros/autorizado \
  --model ~/Desktop/modelos/lbph.yml \
  --name "Persona autorizada"
```

Qué hace el comando: COPIA (no mueve) las imágenes a la ubicación privada,
asigna `model_label=1` (queda idéntico al base), y **entrena un modelo nuevo**
en `{data_dir}/modelos/modelo_lbph.yml`. El modelo original del base queda
intacto en `~/Desktop/modelos/`.

## 6. Crear el primer administrador

```bash
device/.venv/bin/python -m device.cli init-admin --password 'CONTRASEÑA_FUERTE'
```

Solo se permite el first run: si ya existe un admin habilitado, el comando
`init-admin` reemplaza la contraseña (revisión manual). La cuenta admin NO
tiene relacion con el reconocimiento facial.

## 7. Arrancar el servicio

```bash
device/.venv/bin/python -m device.cli serve
# API en http://127.0.0.1:5000 (no exponer el 5000 a Internet)
```

Verificación rápida en otra terminal:

```bash
curl -s http://127.0.0.1:5000/api/health
```

## 8. Panel web

```bash
cd web
npm install
npm run dev
# Panel en http://<ip-de-la-pi>:5173
```

Para producción: `npm run build` + `_serve_ dist` con un Nginx local o Vercel
(ver remote-access.md para exponer de manera segura).

## 9. Copia de seguridad

```bash
# los datos privados viven aparte; respalda solo eso:
tar -czf /home/saffu1/proyectoc3_backup_$(date +%F).tar.gz \
    -C /home/saffu1/.local/share proyectoC3
chmod 600 /home/saffu1/proyectoc3_backup_*.tar.gz
```

## 10. Pruebas automatizadas

```bash
device/.venv/bin/python -m pytest device/tests -q
```

42 pruebas, **sin webcam**: cubren personas autorizadas/desconocidas/
suspendidas/revocadas/vencidas/sin rol, permisos vencidos, modelo inexistente
o corrupto, cámara desconectada, BD bloqueada, dedup de eventos al sincro,
etiquetas LBPH duplicadas, y la cámara en vivo bloqueada por sesión no
autenticada.
