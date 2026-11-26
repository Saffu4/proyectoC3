"""Operaciones sobre personas compartidas por la API web y la pantalla TFT.

Un solo lugar para crear, cambiar estado, borrar y reentrenar, para que la
pantalla táctil y el panel web hagan exactamente lo mismo (y queden en audit_log).
"""
from __future__ import annotations

import uuid

from . import auth, capture_service, db
from .face_recognizer import ModelUnavailableError, get_recognizer, invalidate_shared

STATUSES = ("active", "suspended", "revoked")
PIN_SETTING = "tft_admin_pin_hash"


def audit(action: str, detail: str | None, actor: str = "pantalla") -> None:
    db.execute(
        "INSERT INTO audit_log (action, actor, detail, timestamp) VALUES (?, ?, ?, ?)",
        (action, actor, detail, db.utcnow_iso()),
    )


def create_person(full_name: str, roles=("user",), actor: str = "pantalla") -> str:
    full_name = " ".join(full_name.split())
    if len(full_name) < 2:
        raise ValueError("El nombre debe tener al menos 2 letras")
    pid = str(uuid.uuid4())
    now = db.utcnow_iso()
    db.execute(
        "INSERT INTO people (id, full_name, document_id, status, expires_at, created_at, updated_at) "
        "VALUES (?, ?, NULL, 'active', NULL, ?, ?)",
        (pid, full_name, now, now),
    )
    for role in roles:
        row = db.query("SELECT id FROM roles WHERE name = ?", (role,))
        if row:
            db.execute("INSERT OR IGNORE INTO person_roles (person_id, role_id) VALUES (?, ?)",
                       (pid, row[0]["id"]))
    audit("person_create", f"id={pid} name={full_name}", actor)
    return pid


def set_status(person_id: str, status: str, actor: str = "pantalla") -> bool:
    if status not in STATUSES:
        raise ValueError("status inválido")
    n = db.execute("UPDATE people SET status=?, updated_at=? WHERE id=?",
                   (status, db.utcnow_iso(), person_id))
    if n:
        verb = {"active": "activate", "suspended": "suspend", "revoked": "revoke"}[status]
        audit(f"person_{verb}", f"id={person_id}", actor)
    return bool(n)


def retrain(actor: str = "pantalla") -> int | None:
    """Reentrena con todas las fotos habilitadas. None si no hay ninguna."""
    invalidate_shared()
    try:
        used = get_recognizer().train()
    except ModelUnavailableError:
        used = None
    invalidate_shared()
    audit("model_train", f"images={used}", actor)
    return used


def delete_person(person_id: str, actor: str = "pantalla") -> dict | None:
    """Borra fotos, perfil y persona; reentrena para que su rostro deje de existir
    en el modelo. Los eventos quedan con person_id NULL (retención de auditoría)."""
    if not db.query("SELECT id FROM people WHERE id=?", (person_id,)):
        return None
    images = capture_service.delete_face_images(person_id)
    db.execute("DELETE FROM face_profiles WHERE person_id=?", (person_id,))
    db.execute("DELETE FROM people WHERE id=?", (person_id,))
    used = retrain(actor)
    audit("person_delete", f"id={person_id} images={images} retrained={used is not None}", actor)
    return {"face_images_deleted": images, "model_retrained": used is not None}


def list_people() -> list[dict]:
    rows = db.query("SELECT id, full_name, status FROM people ORDER BY full_name COLLATE NOCASE")
    out = []
    for r in rows:
        d = dict(r)
        d["photos"] = len(capture_service.list_saved_images(d["id"]))
        out.append(d)
    return out


def get_person(person_id: str) -> dict | None:
    rows = db.query("SELECT id, full_name, status FROM people WHERE id=?", (person_id,))
    if not rows:
        return None
    d = dict(rows[0])
    d["photos"] = len(capture_service.list_saved_images(person_id))
    return d


# ------------------------------------------------- PIN de administración (TFT)

def set_admin_pin(pin: str) -> None:
    if not pin.isdigit() or not 4 <= len(pin) <= 8:
        raise ValueError("El PIN debe tener entre 4 y 8 dígitos")
    db.set_setting(PIN_SETTING, auth.hash_password(pin))
    audit("tft_pin_set", None, "cli")


def has_admin_pin() -> bool:
    return bool(db.get_setting(PIN_SETTING))


def verify_admin_pin(pin: str) -> bool:
    stored = db.get_setting(PIN_SETTING)
    return bool(stored) and auth.verify_password(pin, stored)
