"""API REST del dispositivo (Flask). Todos los endpoints administrativos están
autenticados; el reconocimiento corre como servicio independiente de las rutas."""
from __future__ import annotations

import functools
import secrets
import time
import uuid
from pathlib import Path
from datetime import datetime

import cv2
from flask import Flask, Response, jsonify, request, send_from_directory

from . import access_service, auth, camera, capture_service, config, db, event_service, sync_service
from .access_service import AccessDecision
from .camera import CameraDisconnectedError
from .face_detector import FaceDetector
from .face_recognizer import ModelUnavailableError, get_recognizer, invalidate_shared

# Panel web precompilado (device/webapp): TODO en la Pi, sin Node ni Vercel.
WEBAPP_DIR = Path(__file__).resolve().parent / "webapp"

app = Flask(__name__)
app.config["SECRET_KEY"] = config.FLASK_SECRET

_detector: FaceDetector | None = None
_sync_last: dict | None = None

# ------------------------------------------------------------------ utilidades


def _error(message: str, status: int, code: str = "error"):
    return jsonify({"error": code, "message": message}), status


def require_admin(fn):
    """Decorador de autenticación en servidor. No se confía en roles de cliente."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token = None
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header.removeprefix("Bearer ").strip()
        info = auth.verify_session(token)
        if not info:
            return _error("Sesión administrativa requerida", 401, "unauthorized")
        request.admin = info  # type: ignore[attr-defined]
        return fn(*args, **kwargs)

    return wrapper


def log_audit(action: str, detail: str | None = None):
    actor = getattr(request, "admin", {}).get("username", "system")
    db.execute(
        "INSERT INTO audit_log (action, actor, detail, timestamp) VALUES (?, ?, ?, ?)",
        (action, actor, detail, db.utcnow_iso()),
    )


def _body_json() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _uuid_or_400(value: str) -> str:
    uuid.UUID(value)
    return value


@app.before_request
def _init():
    global _detector
    if _detector is None:
        try:
            _detector = FaceDetector()
        except RuntimeError:
            _detector = None


# ---------------------------------------------------------------------- health


@app.get("/api/health")
def health():
    return jsonify({"ok": True, "time": db.utcnow_iso(), "version": "1.0.0"})


@app.get("/api/device/status")
@require_admin
def device_status():
    cam_ok = True
    cam_error = None
    try:
        camera.get_source().read()
    except CameraDisconnectedError as exc:
        cam_ok, cam_error = False, str(exc)
    model_ok = get_recognizer().is_trained()
    profiles = db.query("SELECT COUNT(*) AS c FROM face_profiles WHERE enabled=1")[0]["c"]
    age = sync_service.policy_sync_age_hours()
    return jsonify(
        {
            "device_id": config.device_id(),
            "camera": {"available": cam_ok, "error": cam_error},
            "model": {"trained": model_ok, "threshold": config.LBPH_THRESHOLD,
                      "faces_trained": profiles},
            "sync": {
                "enabled": config.SYNC_ENABLED,
                "last_policy_sync": db.get_setting("last_policy_sync"),
                "age_hours": age,
                "stale": age is None or age > config.POLICY_MAX_AGE_HOURS or (age == 0 and config.SYNC_ENABLED),
            },
            "events": event_service.summary(),
            "pending_events": event_service.summary()["unsynced"],
        }
    )


# ----------------------------------------------------------------------- login


@app.post("/api/auth/login")
def login():
    body = _body_json()
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or not password:
        return _error("username y password requeridos", 400, "bad_request")
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "-")
    try:
        sess = auth.login(username, password, ip=ip)
    except PermissionError as exc:
        return _error(str(exc), 429, "too_many_attempts")
    if not sess:
        return _error("Credenciales inválidas", 401, "invalid_credentials")
    return jsonify(sess)


@app.post("/api/auth/logout")
def logout():
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    auth.logout(token)
    return jsonify({"ok": True})


# --------------------------------------------------------------------- personas


def _new_person(body: dict) -> dict:
    full_name = str(body.get("full_name", "")).strip()
    if not full_name:
        raise ValueError("full_name requerido")
    status = str(body.get("status", "active"))
    if status not in ("active", "suspended", "revoked"):
        raise ValueError("status inválido")
    expires_at = body.get("expires_at")
    if expires_at is not None:
        datetime.fromisoformat(str(expires_at))  # validación
    roles = body.get("roles", ["user"])
    if not isinstance(roles, list):
        raise ValueError("roles debe ser una lista")
    return {
        "id": str(uuid.uuid4()),
        "full_name": full_name,
        "document_id": str(body.get("document_id") or "") or None,
        "expires_at": expires_at,
        "status": status,
        "roles": [str(r) for r in roles],
    }


@app.get("/api/people")
@require_admin
def people_list():
    rows = db.query(
        "SELECT p.id, p.full_name, p.document_id, p.status, p.expires_at, p.created_at, p.updated_at, "
        "GROUP_CONCAT(r.name) AS roles "
        "FROM people p LEFT JOIN person_roles pr ON pr.person_id = p.id "
        "LEFT JOIN roles r ON r.id = pr.role_id GROUP BY p.id ORDER BY p.full_name"
    )
    out = []
    for r in rows:
        d = dict(r)
        d["roles"] = d["roles"].split(",") if d["roles"] else []
        d["expires_valid"] = None
        out.append(d)
    return jsonify(out)


@app.post("/api/people")
@require_admin
def people_create():
    body = _body_json()
    try:
        data = _new_person(body)
    except ValueError as exc:
        return _error(str(exc), 400, "bad_request")
    now = db.utcnow_iso()
    db.execute(
        "INSERT INTO people (id, full_name, document_id, status, expires_at, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (data["id"], data["full_name"], data["document_id"], data["status"], data["expires_at"], now, now),
    )
    for role_name in data["roles"]:
        role_row = db.query("SELECT id FROM roles WHERE name = ?", (role_name,))
        if role_row:
            db.execute(
                "INSERT OR IGNORE INTO person_roles (person_id, role_id) VALUES (?, ?)",
                (data["id"], role_row[0]["id"]),
            )
    log_audit("person_create", f"id={data['id']} name={data['full_name']}")
    return jsonify({"id": data["id"]}), 201


@app.get("/api/people/<person_id>")
@require_admin
def person_get(person_id: str):
    try:
        _uuid_or_400(person_id)
    except ValueError:
        return _error("id inválido", 400, "bad_request")
    rows = db.query("SELECT * FROM people WHERE id = ?", (person_id,))
    if not rows:
        return _error("Persona no encontrada", 404, "not_found")
    p = dict(rows[0])
    p["roles"] = [r["name"] for r in db.query(
        "SELECT r.name FROM roles r JOIN person_roles pr ON pr.role_id = r.id WHERE pr.person_id = ?",
        (person_id,),
    )]
    p["face_profile"] = None
    fpr = db.query("SELECT id, model_label, enabled, created_at FROM face_profiles WHERE person_id=?", (person_id,))
    if fpr:
        p["face_profile"] = dict(fpr[0])
        p["face_images"] = capture_service.list_saved_images(person_id)
        p["face_images_count"] = len(p["face_images"])
    return jsonify(p)


@app.patch("/api/people/<person_id>")
@require_admin
def person_patch(person_id: str):
    body = _body_json()
    allowed = {"full_name", "document_id", "expires_at", "status"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return _error("Nada para actualizar", 400, "bad_request")
    if "status" in updates and updates["status"] not in ("active", "suspended", "revoked"):
        return _error("status inválido", 400, "bad_request")
    if "expires_at" in updates and updates["expires_at"] is not None:
        try:
            datetime.fromisoformat(str(updates["expires_at"]))
        except ValueError:
            return _error("expires_at con formato inválido", 400, "bad_request")
    try:
        _uuid_or_400(person_id)
    except ValueError:
        return _error("id inválido", 400, "bad_request")
    sets = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [db.utcnow_iso(), person_id]
    n = db.execute(f"UPDATE people SET {sets}, updated_at = ? WHERE id = ?", tuple(values))  # type: ignore
    if not n:
        return _error("Persona no encontrada", 404, "not_found")
    if "roles" in body:
        role_rows = db.query("SELECT id, name FROM roles")
        wanted = set(body["roles"])
        db.execute("DELETE FROM person_roles WHERE person_id = ?", (person_id,))
        for r in role_rows:
            if r["name"] in wanted:
                db.execute(
                    "INSERT OR IGNORE INTO person_roles (person_id, role_id) VALUES (?, ?)",
                    (person_id, r["id"]),
                )
    log_audit("person_update", f"id={person_id} fields={','.join(updates)}")
    return jsonify({"ok": True})


@app.post("/api/people/<person_id>/suspend")
@require_admin
def person_suspend(person_id: str):
    n = db.execute("UPDATE people SET status='suspended', updated_at=? WHERE id=?",
                   (db.utcnow_iso(), person_id))
    if not n:
        return _error("Persona no encontrada", 404, "not_found")
    log_audit("person_suspend", f"id={person_id}")
    return jsonify({"ok": True, "status": "suspended"})


@app.post("/api/people/<person_id>/revoke")
@require_admin
def person_revoke(person_id: str):
    n = db.execute("UPDATE people SET status='revoked', updated_at=? WHERE id=?",
                   (db.utcnow_iso(), person_id))
    if not n:
        return _error("Persona no encontrada", 404, "not_found")
    log_audit("person_revoke", f"id={person_id}")
    return jsonify({"ok": True, "status": "revoked"})


@app.post("/api/people/<person_id>/activate")
@require_admin
def person_activate(person_id: str):
    n = db.execute("UPDATE people SET status='active', updated_at=? WHERE id=?",
                   (db.utcnow_iso(), person_id))
    if not n:
        return _error("Persona no encontrada", 404, "not_found")
    log_audit("person_activate", f"id={person_id}")
    return jsonify({"ok": True, "status": "active"})


@app.delete("/api/people/<person_id>")
@require_admin
def person_delete(person_id: str):
    """Eliminación con política de retención: borra imágenes biométricas y
    eventos quedan con person_id NULL (retención auditiva); modelo hay que reentrenar."""
    rows = db.query("SELECT id FROM people WHERE id=?", (person_id,))
    if not rows:
        return _error("Persona no encontrada", 404, "not_found")
    saved = capture_service.delete_face_images(person_id)
    db.execute("DELETE FROM face_profiles WHERE person_id=?", (person_id,))
    db.execute("DELETE FROM people WHERE id=?", (person_id,))
    invalidate_shared()
    log_audit("person_delete", f"id={person_id} images={saved}")
    return jsonify({"ok": True, "face_images_deleted": saved})


@app.post("/api/people/<person_id>/capture")
@require_admin
def person_capture(person_id: str):
    body = _body_json()
    count = int(body.get("count", 10))
    try:
        saved = capture_service.capture_faces(person_id, count=count)
    except (capture_service.CaptureError, CameraDisconnectedError) as exc:
        code = "camera_disconnected" if isinstance(exc, CameraDisconnectedError) else "capture_error"
        return _error(str(exc), 503 if code == "camera_disconnected" else 400, code)
    log_audit("faces_capture", f"id={person_id} saved={saved['saved']}")
    return jsonify(saved), 201


@app.post("/api/people/<person_id>/train")
@require_admin
def person_train(person_id: str):
    """Reentrena el modelo con TODAS las imágenes habilitadas de TODAS las personas.
    Verificar coherencia de etiquetas: cada label debe existir en face_profiles."""
    try:
        rows = db.query("SELECT model_label FROM face_profiles")
        labels = [int(r["model_label"]) for r in rows]
        if len(labels) != len(set(labels)):
            return _error("Etiquetas duplicadas en face_profiles; corregir antes de entrenar", 409, "labels_conflict")
        used = get_recognizer().train()
        invalidate_shared()
    except ModelUnavailableError as exc:
        return _error(str(exc), 409, "train_failed")
    log_audit("model_train", f"trigger=person id={person_id} images={used}")
    return jsonify({"ok": True, "images_used": used}), 201


# ---------------------------------------------------------------------- eventos


@app.get("/api/access-events")
@require_admin
def access_events():
    limit = max(1, min(int(request.args.get("limit", 50)), 500))
    return jsonify(event_service.recent(limit))


# ---------------------------------------------------------------------- cámara

@app.post("/api/camera/stream-token")
@require_admin
def camera_stream_token():
    """Emite token efímero (10 min, solo lectura) para el <img> del panel.
    Falla pronto si la cámara está desconectada o no entrega frames."""
    camera.get_source().read()
    tok = auth.issue_stream_token()
    return jsonify({"token": tok, "ttl_seconds": auth.STREAM_TOKEN_TTL_SECONDS})


@app.post("/api/camera/revoke-token")
@require_admin
def camera_revoke_token():
    auth.revoke_stream_tokens()
    log_audit("stream_token_revoked", None)
    return jsonify({"ok": True})


@app.get("/api/camera/stream")
def camera_stream():
    """MJPEG con autorización PROPIA: sesión admin O token de stream efímero.
    El <img> del navegador no puede mandar headers; por eso existe el token."""
    token = request.args.get("t")
    header = request.headers.get("Authorization", "")
    session_ok = auth.verify_session(header.removeprefix("Bearer ").strip())
    if not (session_ok or auth.verify_stream_token(token)):
        return _error("Flujo de cámara no autorizado", 401, "unauthorized")

    def gen():
        detector = _detector or FaceDetector()
        while True:
            try:
                frame = camera.get_source().read()
            except CameraDisconnectedError:
                yield b"--frame\r\nContent-Type: text/plain\r\n\r\ncamera offline\r\n"
                time.sleep(0.5)
                continue
            for (x, y, w, h) in detector.detect(frame):
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 200, 0), 2)
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            time.sleep(0.08)

    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


# ----------------------------------------------------------------------- roles


@app.get("/api/roles")
@require_admin
def roles_list():
    rows = db.query(
        "SELECT r.id, r.name, r.description, GROUP_CONCAT(p.code) AS permissions "
        "FROM roles r LEFT JOIN role_permissions rp ON rp.role_id=r.id "
        "LEFT JOIN permissions p ON p.id=rp.permission_id GROUP BY r.id ORDER BY r.id"
    )
    out = []
    for r in rows:
        d = dict(r)
        d["permissions"] = d["permissions"].split(",") if d["permissions"] else []
        out.append(d)
    return jsonify(out)


@app.post("/api/roles")
@require_admin
def roles_create():
    body = _body_json()
    name = str(body.get("name", "")).strip().lower()
    if not name or not name.replace("_", "").isalnum():
        return _error("name inválido", 400, "bad_request")
    db.execute(
        "INSERT OR IGNORE INTO roles (name, description) VALUES (?, ?)",
        (name, str(body.get("description", ""))),
    )
    if isinstance(body.get("permissions"), list):
        for code in body["permissions"]:
            db.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) "
                "SELECT id, (SELECT id FROM permissions WHERE code=?) FROM roles WHERE name=?",
                (code, name),
            )
    log_audit("role_create", f"name={name}")
    return jsonify({"ok": True}), 201


@app.patch("/api/roles/<int:role_id>")
@require_admin
def roles_patch(role_id: int):
    body = _body_json()
    if "description" in body:
        db.execute("UPDATE roles SET description=? WHERE id=?", (str(body["description"]), role_id))
    if isinstance(body.get("permissions"), list):
        db.execute("DELETE FROM role_permissions WHERE role_id=?", (role_id,))
        for code in body["permissions"]:
            db.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) "
                "SELECT ?, (SELECT id FROM permissions WHERE code=?)",
                (role_id, code),
            )
    log_audit("role_update", f"id={role_id}")
    return jsonify({"ok": True})


# ------------------------------------------------------------------- settings


@app.get("/api/settings")
@require_admin
def settings_get():
    rows = db.query("SELECT key, value FROM settings")
    return jsonify({r["key"]: r["value"] for r in rows})


@app.patch("/api/settings")
@require_admin
def settings_patch():
    body = _body_json()
    for key, value in body.items():
        if key in ("device_id",):  # protegido
            continue
        db.set_setting(key, str(value))
    log_audit("settings_update", ",".join(body.keys()))
    return jsonify({"ok": True})


# ------------------------------------------------------------------- sync


@app.post("/api/sync/now")
@require_admin
def sync_now():
    try:
        result = sync_service.run_sync()
    except ConnectionError as exc:
        return _error(str(exc), 502, "sync_unavailable")
    return jsonify(result)


@app.get("/api/audit-log")
@require_admin
def audit_log():
    rows = db.query("SELECT action, actor, detail, timestamp FROM audit_log ORDER BY id DESC LIMIT 100")
    return jsonify([dict(r) for r in rows])


# --------------------------------------------------------------- kiosco/panel


@app.post("/api/access/check")
@require_admin
def access_check():
    """Comprobación manual frente a la cámara: se reconoce, se decide y se loguea.
    No conceder administrador por coincidencia facial: solo welcome/denied."""
    try:
        frame = camera.get_source().read()
        global _detector
        if _detector is None:
            _detector = FaceDetector()
        faces = _detector.detect(frame)
        if not faces:
            resp = jsonify({"category": "denied_unknown", "decision": False,
                            "message": "No se detectó ningún rostro"})
            return resp, 404
        (x, y, w, h) = faces[0]
        match = get_recognizer().predict(frame[y:y + h, x:x + w])
        decision = access_service.decide_from_recognition(match)
    except ModelUnavailableError as exc:
        event_service.log_access(person_id=None, result="denied", reason=str(exc),
                                 category="denied_model")
        return jsonify({"category": "denied_model", "decision": False, "message": str(exc)}), 503
    except CameraDisconnectedError as exc:
        return jsonify({"category": "denied_camera", "decision": False, "message": str(exc)}), 503
    except Exception as exc:
        event_service.log_access(person_id=None, result="denied", reason=str(exc),
                                 category="denied_internal_error")
        return jsonify({"category": "denied_internal_error", "decision": False, "message": str(exc)}), 500
    if decision.granted:
        log_audit("access_check_granted", f"person={decision.person_id}")
    resp = jsonify({"category": decision.category, "decision": decision.granted,
                    "display_name": decision.display_name, "confidence": decision.confidence})
    return resp, (200 if decision.granted else 403)


@app.post("/api/kiosk/evaluate")
def kiosk_evaluate():
    """Modo kiosco: pantalla dedicada. Requiere token de sesión kiosco generado
    en el panel; no se pide login admin, pero el token es viejo y con expiración
    corta (ver docs/security.md). En esta versión el token lo emite el panel."""
    body = _body_json()
    token = request.headers.get("X-Kiosk-Token", body.get("token", ""))
    expected = db.get_setting("kiosk_token")
    if not (expected and token):
        return _error("Token de kiosco inválido", 401, "unauthorized")
    if not secrets.compare_digest(str(token), expected):
        return _error("Token de kiosco inválido", 401, "unauthorized")
    decision = None
    try:
        frame = camera.get_source().read()
        faces = (_detector or FaceDetector()).detect(frame)
        if not faces:
            return jsonify({"category": "denied_unknown", "decision": False,
                            "message": "No se detectó ningún rostro"}), 404
        (x, y, w, h) = faces[0]
        match = get_recognizer().predict(frame[y:y + h, x:x + w])
        decision = access_service.decide_from_recognition(match)
    except ModelUnavailableError as exc:
        event_service.log_access(person_id=None, result="denied", reason=str(exc),
                                 category="denied_model")
        return jsonify({"category": "denied_model", "decision": False}), 503
    except CameraDisconnectedError as exc:
        return jsonify({"category": "denied_camera", "decision": False}), 503
    # el token kiosco es de un solo uso: se rota tras cada evaluación
    new_token = secrets.token_urlsafe(24)
    db.set_setting("kiosk_token", new_token)
    return jsonify(
        {"category": decision.category, "decision": decision.granted,
         "display_name": decision.display_name, "next_token": new_token}
    ), (200 if decision.granted else 403)


# ----------------------------------------------------------------------- SPA

@app.get("/")
@app.get("/ui/<path:_any>")
def spa_index():
    """Panel web (build precompilado). Frontend y API en el mismo origen."""
    if not (WEBAPP_DIR / "index.html").exists():
        return _error("Panel web no incluido en esta instalación", 404, "webapp_missing")
    return send_from_directory(WEBAPP_DIR, "index.html")


@app.get("/assets/<path:asset_path>")
def spa_assets(asset_path: str):
    if not (WEBAPP_DIR / "assets").exists():
        return _error("Panel web no incluido en esta instalación", 404, "webapp_missing")
    return send_from_directory(WEBAPP_DIR / "assets", asset_path, max_age=3600)


# ----------------------------------------------------------------------- error app

@app.errorhandler(404)
def not_found(e):
    # los errores de página (no API) redirigen al SPA
    if not request.path.startswith("/api/"):
        return spa_index()
    return _error("Endpoint no encontrado", 404, "not_found")


@app.errorhandler(500)
def internal_error(e):
    db.execute(
        "INSERT INTO audit_log (action, actor, detail, timestamp) VALUES (?, ?, ?, ?)",
        ("http_500", "system", str(e), db.utcnow_iso()),
    )
    return _error("Error interno", 500, "internal_error")
