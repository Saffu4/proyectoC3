"""Configuración central del servicio del dispositivo.

Lee variables de entorno (archivo .env opcional) y define rutas de datos que
deben permanecer FUERA del repositorio Git (biometría, modelo, base de datos).
"""
from __future__ import annotations

import os
import secrets
import uuid
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def _load_env_file() -> None:
    """Crea cargue mínimo de .env (como python-dotenv pero sin dependencia externa)."""
    env_candidate = Path(os.getcwd()) / ".env"
    if env_candidate.exists():
        for line in env_candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file()


def data_dir() -> Path:
    """Directorio de datos privados. En producción: /home/saffu1/.local/share/proyectoC3."""
    raw = os.environ.get("PROYECTO_C3_DATA")
    base = Path(raw) if raw else Path.cwd() / "data"
    return base


def faces_dir(person_id: str | None = None) -> Path:
    base = data_dir() / "rostros"
    return base / person_id if person_id else base


def models_dir() -> Path:
    return data_dir() / "modelos"


DB_PATH = data_dir() / "proyecto_c3.sqlite"

# --- Cámara ---
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
CAPTURE_WIDTH = int(os.environ.get("CAPTURE_WIDTH", "640"))
CAPTURE_HEIGHT = int(os.environ.get("CAPTURE_HEIGHT", "480"))
# Igual que el pipeline base (registrar_rostro.py / entrenar_modelo.py):
# rostro normalizado a 200x200 con equalizeHist. NO cambiar sin reentrenar.
CAPTURE_SIZE = int(os.environ.get("CAPTURE_SIZE", "200"))
# Margen alrededor del rostro al capturar (factor, igual al base: 0.15)
FACE_MARGIN = float(os.environ.get("FACE_MARGIN", "0.15"))
# Segundos entre capturas de rostro (ritmo del base: 0.4)
CAPTURE_PACE_SECONDS = float(os.environ.get("CAPTURE_PACE_SECONDS", "0.4"))

# Cascade: el base usa /usr/share/opencv4/haarcascades. Probamos esa ruta y la del paquete pip.
CASCADE_CANDIDATES = (
    os.environ.get("CASCADE_PATH", "/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml"),
    str(PACKAGE_DIR / "assets" / "haarcascade_frontalface_default.xml"),
    "haarcascades/haarcascade_frontalface_default.xml",
)

# --- Flask ---
FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
FLASK_SECRET = os.environ.get("FLASK_SECRET") or secrets.token_hex(32)
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# --- Reconocimiento ---
# Distancia LBPH; valor inicial del base (65.0). Calibrar con datos reales
# (docs/authorization-guide.md). NO es una probabilidad.
LBPH_THRESHOLD = float(os.environ.get("LBPH_THRESHOLD", "65"))

# --- Sincronización ---
SYNC_ENABLED = os.environ.get("SYNC_ENABLED", "false").lower() == "true"
SYNC_INTERVAL_SECONDS = int(os.environ.get("SYNC_INTERVAL_SECONDS", "60"))
POLICY_MAX_AGE_HOURS = float(os.environ.get("POLICY_MAX_AGE_HOURS", "72"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

# --- Seguridad ---
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_SECONDS", str(8 * 3600)))
LOGIN_MAX_ATTEMPTS = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(os.environ.get("LOGIN_LOCKOUT_SECONDS", "60"))


def ensure_data_dirs() -> None:
    """Crea el árbol de datos privados con permisos restrictivos (0o700)."""
    for d in (data_dir(), faces_dir(), models_dir()):
        d.mkdir(parents=True, exist_ok=True)
        try:
            d.chmod(0o700)  # no-op en Windows, efectivo en Raspberry Pi
        except OSError:
            pass


def device_id() -> str:
    """Identificador estable del dispositivo, persistido en settings."""
    from . import db

    value = db.get_setting("device_id")
    if not value:
        name = os.environ.get("DEVICE_NAME", "raspberry-pi-5")
        value = f"{name}-{uuid.uuid4().hex[:8]}"
        db.set_setting("device_id", value)
    return value
