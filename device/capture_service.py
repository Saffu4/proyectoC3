"""Captura de rostros para registrar una persona (flujo administrativo).

Pasos: persona debe estar creada y activa -> se capturan N frames con rostro
detectable -> se guardan en rostros/<person_id>/ (ubicación privada) ->
se crea/actualiza face_profiles con una única model_label estable."""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

import cv2

from . import camera, db, config
from .face_detector import FaceDetector
from .face_recognizer import next_model_label, load_face_to_train

MIN_FACE_PX = 80  # ancho mínimo de la cara para considerarla utilizable


class CaptureError(Exception):
    pass


def ensure_face_profile_person(*, full_name: str, document_id: str | None = None,
                               roles=("user",), status: str = "active",
                               expires_at: str | None = None) -> str:
    """Crea la persona + su perfil facial (para importaciones u otras utilidades).
    Devuelve el person_id."""
    import uuid

    pid = str(uuid.uuid4())
    now = db.utcnow_iso()
    db.execute(
        "INSERT INTO people (id, full_name, document_id, status, expires_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pid, full_name, document_id, status, expires_at, now, now),
    )
    for role in roles:
        row = db.query("SELECT id FROM roles WHERE name = ?", (role,))
        if row:
            db.execute("INSERT OR IGNORE INTO person_roles (person_id, role_id) VALUES (?, ?)",
                       (pid, row[0]["id"]))
    ensure_face_profile(pid)
    return pid


def ensure_face_profile(person_id: str) -> dict:
    """Garantiza que la persona tenga un perfil facial con etiqueta estable."""
    rows = db.query("SELECT * FROM face_profiles WHERE person_id = ?", (person_id,))
    if rows:
        return dict(rows[0])
    now = db.utcnow_iso()
    label = next_model_label()
    profile_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO face_profiles (id, person_id, model_label, enabled, created_at) "
        "VALUES (?, ?, ?, 1, ?)",
        (profile_id, person_id, label, now),
    )
    return {"id": profile_id, "person_id": person_id, "model_label": label, "enabled": 1, "created_at": now}


def capture_faces(person_id: str, count: int = 10, timeout_s: float = 30.0) -> dict:
    """Captura `count` frames con rostro detectable y los guarda en disco.

    Devuelve cuántos rostros se guardaron. Lanza CameraDisconnectedError si la
    cámara no entrega frames."""
    if count < 1 or count > 50:
        raise CaptureError("count debe estar entre 1 y 50")
    person_rows = db.query("SELECT id, status FROM people WHERE id = ?", (person_id,))
    if not person_rows:
        raise CaptureError("Persona no encontrada")
    if person_rows[0]["status"] != "active":
        raise CaptureError("Solo se puede capturar rostros de personas activas")

    profile = ensure_face_profile(person_id)
    detector = FaceDetector()
    folder = config.faces_dir(person_id)
    config.ensure_data_dirs()
    folder.mkdir(parents=True, exist_ok=True)
    folder.chmod(0o700)

    saved = 0
    attempts = 0
    max_attempts = int(timeout_s * 24)  # ritmo del base (~0.4 s por guardado)
    while saved < count and attempts < max_attempts:
        attempts += 1
        try:
            frame = camera.get_source().read()
        except camera.CameraDisconnectedError:
            # misma clase que el resto del sistema: una sola excepción de cámara
            raise
        faces = detector.detect(frame)
        # misma regla que el base: la cara más grande del encuadre
        faces = sorted(faces, key=lambda c: c[2] * c[3], reverse=True)
        for (x, y, w, h) in faces:
            if w < MIN_FACE_PX:
                continue
            # margen alrededor del rostro (igual que registrar_rostro.py base)
            margen_x = int(w * config.FACE_MARGIN)
            margen_y = int(h * config.FACE_MARGIN)
            H, W = frame.shape[:2]
            x1, y1 = max(0, x - margen_x), max(0, y - margen_y)
            x2, y2 = min(W, x + w + margen_x), min(H, y + h + margen_y)
            roi = frame[y1:y2, x1:x2]
            gray = load_face_to_train(roi)  # gris + resize 200 + ecualización
            filename = folder / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{int(time.monotonic()*1000)%10000}_{saved}.jpg"
            # volvemos a BGR para guardar consistente con el pipeline original (jpg)
            cv2.imwrite(str(filename), gray)
            saved += 1
            break  # una cara por frame
        if saved < count:
            time.sleep(config.CAPTURE_PACE_SECONDS)
    if saved < count:
        raise CaptureError(
            f"Solo se capturaron {saved}/{count} rostros: ilumina mejor y acércate (perfil de todos modos actualizado)"
        )
    return {"profile_id": profile["id"], "model_label": profile["model_label"], "saved": saved}


def list_saved_images(person_id: str) -> list[str]:
    folder = config.faces_dir(person_id)
    if not folder.exists():
        return []
    return [p.name for p in sorted(folder.glob("*.jpg"))]


def delete_face_images(person_id: str) -> int:
    """Elimina las imágenes biométricas de una persona (política de retención).
    No borra el modelo: hay que reentrenar tras eliminar."""
    import shutil

    folder = config.faces_dir(person_id)
    if not folder.exists():
        return 0
    n = len(list(folder.glob("*.jpg")))
    shutil.rmtree(folder)
    return n
