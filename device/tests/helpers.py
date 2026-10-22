"""Helpers para pruebas: imágenes sintéticas y prospectos de datos."""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from device import config, db, camera  # noqa: E402


def make_face_image(seed: int, size: int = 320) -> np.ndarray:
    """Imagen determinista por semilla (gris + gradiente + ruido) para LBPH.

    Semillas cercanas generan patrones distintos; LBPH distingue el distinto."""
    rng = np.random.default_rng(seed)
    gray = (rng.integers(0, 255, (size, size), dtype=np.uint32) // 2).astype(np.uint8)
    gray = cv2.addWeighted(gray, 0.9, rng.integers(30, 40, (size, size), dtype=np.uint8).astype(np.uint8), 0.1, 0)
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return bgr


def make_test_frame(seed: int = 1, size: int = 320) -> np.ndarray:
    """Frame BGR completo para inyectar como fuente de cámara de prueba."""
    return make_face_image(seed, size)


def create_person(full_name: str, *, status: str = "active", expires_at=None,
                  roles=("user",), document_id: str = None) -> str:
    person_id = __import__("uuid").uuid4().hex
    now = db.utcnow_iso()
    db.execute(
        "INSERT INTO people (id, full_name, document_id, status, expires_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (person_id, full_name, document_id, status, expires_at, now, now),
    )
    for role in roles:
        row = db.query("SELECT id FROM roles WHERE name = ?", (role,))
        if row:
            db.execute("INSERT OR IGNORE INTO person_roles (person_id, role_id) VALUES (?, ?)",
                       (person_id, row[0]["id"]))
    return person_id


def add_face_images(person_id: str, seeds: list[int], *, enabled_profile: bool = True) -> int:
    """Escribe imágenes normalizadas en rostros/<person_id>/ y crea perfil facial.
    Simula el flujo de captura sin webcam."""
    from device.capture_service import ensure_face_profile
    from device.face_recognizer import load_face_to_train

    profile = ensure_face_profile(person_id)
    folder = config.faces_dir(person_id)
    config.ensure_data_dirs()
    folder.mkdir(parents=True, exist_ok=True)
    for i, seed in enumerate(seeds):
        img = load_face_to_train(make_face_image(seed))
        cv2.imwrite(str(folder / f"seed_{seed}_{i}.jpg"), img)
    if not enabled_profile:
        db.execute("UPDATE face_profiles SET enabled=0 WHERE person_id=?", (person_id,))
    return len(seeds)


def set_camera_static(images: list[np.ndarray]) -> camera.StaticSource:
    src = camera.StaticSource(images)
    camera.set_source(src)
    return src


def set_camera_disconnected() -> None:
    camera.set_source(camera.NoCameraSource())


def login_admin(app_client, username="admin", password="Sup3rSecret!234") -> str:
    from device import auth

    auth.init_admin(username, password)
    resp = app_client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()["token"]
