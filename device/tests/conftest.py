"""Configuración compartida de pytest para las pruebas del dispositivo.

Las pruebas de autorización NO requieren webcam: se usan fuentes sintéticas
(StaticSource / NoCameraSource) y datos de prueba en un directorio temporal."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@pytest.fixture()
def device_env(tmp_path, monkeypatch):
    """Entorno aislado: datos privados en tmp_path y cámara simulada."""
    data_dir = tmp_path / "data"
    monkeypatch.setenv("PROYECTO_C3_DATA", str(data_dir))
    monkeypatch.setenv("CAM_SOURCE", "none")
    from device import config, db, camera, face_recognizer, auth

    config.ensure_data_dirs()
    # Umbral de TESTS: las imágenes sintéticas separan a ~5 (mismo rostro) vs
    # ~41 (desconocido). El umbral de producción se calibra con rostros reales
    # (LBPH_THRESHOLD=65, valor heredado del base).
    config.LBPH_THRESHOLD = 20.0
    db.init_db()
    auth._attempts.clear()  # el rate-limit de login no debe sangrar entre tests
    yield config
    camera.set_source(None)
    face_recognizer.invalidate_shared()
    auth.SESSIONS.clear()
