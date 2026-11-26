# proyectoC3 · Control de acceso facial con Raspberry Pi 5

Sistema de reconocimiento facial (OpenCV LBPH) para autorizar el acceso de
personas, con roles, permisos, historial y panel de administración web.

> ⚠️ **Aviso**: el reconocimiento facial es una demostración y puede equivocarse.
> No lo uses como único control para proteger una puerta, dinero o información
> sensible. Mantén siempre una alternativa manual de acceso.

## Arquitectura

```
[Webcam USB] --> device/ (Flask + LBPH + SQLite)  --> API REST local
                       |                                  |
                 reconocimiento + autorización      web/ (React + TS + Vite)
                       |                              panel administrativo
                sync_service  <-->  Supabase (opcional, políticas + eventos)
```

- `device/` — servicio en la Raspberry Pi: cámara en hilo dedicado, detección
  Haar, reconocimiento LBPH, autorización inmediata (funciona SIN Internet),
  eventos con `event_id` único, sincronización diferida con Supabase.
- `web/` — panel administrativo; el backend valida cada operación.
- `backend/supabase/migrations/` — tablas + RLS versionadas.

## Instalación rápida (Raspberry Pi 5)

```bash
# 1. Dependencias Python (en un venv: Debian 13 exige venv para pip)
cd ~/Desktop/proyectoC3
python3 -m venv device/.venv && device/.venv/bin/pip install -r device/requirements.txt

# 2. Datos privados FUERA del repositorio
mkdir -p /home/saffu1/.local/share/proyectoC3
cp .env.example .env   # editar FLASK_SECRET, ADMIN_USERNAME, ADMIN_PASSWORD

# 3. Migrar el proyecto base (no sobreescribe nada; ejecutar desde proyectoC3/)
device/.venv/bin/python -m device.cli import-base          # rostros del base
device/.venv/bin/python -m device.cli init-admin --password 'CONTRASEÑA_FUERTE'

# 4. Panel web
cd web && npm install && npm run dev
```

Documentación completa:

| Doc | Contenido |
|---|---|
| [docs/installation.md](docs/installation.md) | Instalación paso a paso en la Pi |
| [docs/register-person.md](docs/register-person.md) | Registrar una persona |
| [docs/revoke-permissions.md](docs/revoke-permissions.md) | Revocar/suspender permisos |
| [docs/deployment-local.md](docs/deployment-local.md) | Despliegue local (autoarranque) |
| [docs/remote-access.md](docs/remote-access.md) | Acceso remoto seguro (VPN) |
| [docs/security.md](docs/security.md) | Seguridad, retención y riesgos |
| [docs/authorization-guide.md](docs/authorization-guide.md) | Calibración del umbral LBPH |
| [device/tests/](device/tests/) | 64 pruebas automatizadas (`pytest device/tests`) |

## Compatibilidad con el proyecto base

Los scripts originales (`detector.py`, `registrar_rostro.py`,
`entrenar_modelo.py`) **no se tocan**. El nuevo servicio reutiliza:

- mismo preprocesamiento: gris → crop margen 15% → 200×200 → equalizeHist
  (desde la rama `fix/revision-seguridad` el recorte con margen se aplica
  también al RECONOCER, no solo al capturar: `face_recognizer.crop_face`)
- mismo modelo LBPH (`cv2.face`), carpeta de rostros y ritmo de captura
- umbral LBPH heredado (65.0) — recalibrable

Diferencias intencionadas:

- el modelo base tenía **una sola persona con etiqueta 1**; el nuevo esquema
  asigna `model_label` incrementales (EL PRIMERO SIGUE SIENDO 1) registrándolas
  en la tabla `face_profiles` (SQLite). Las etiquetas de personas borradas
  **nunca se reutilizan** (contador `model_label_counter`) y al borrar una
  persona el modelo se reentrena. Ver `device/face_recognizer.py`.
- `/panel` ya no se protege solo con el reconocimiento: hay sesión
  administrativa real en servidor.

## Organización del repositorio

Los datos biométricos y la base de datos **NO están en Git**:

```
proyectoC3/            ← código (Git)
{data_dir}/            ← rostros/, modelos/, *.sqlite  (0o700, fuera de Git)
```
