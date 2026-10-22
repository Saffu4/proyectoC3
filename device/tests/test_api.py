"""Pruebas de la API REST: autenticación, permisos y endpoints principales."""
from __future__ import annotations

import pytest

from device import camera, capture_service, db
from device.app import app
from . import helpers


def client():
    app.config["TESTING"] = True
    return app.test_client()


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ----------------------------------------------------------------- auth básica

def test_health_sin_autenticacion(device_env):
    resp = client().get("/api/health")
    assert resp.status_code == 200 and resp.get_json()["ok"]


def test_endpoint_admin_requiere_sesion(device_env):
    resp = client().get("/api/people")
    assert resp.status_code == 401
    resp = client().get("/api/access-events")
    assert resp.status_code == 401


def test_login_invalido(device_env):
    from device import auth

    auth.init_admin("admin", "Sup3rSecret!234")
    resp = client().post("/api/auth/login", json={"username": "admin", "password": "malas"})
    assert resp.status_code == 401


def test_login_rate_limit(device_env):
    from device import auth

    auth.init_admin("admin", "Sup3rSecret!234")
    c = client()
    for _ in range(6):
        resp = c.post("/api/auth/login", json={"username": "admin", "password": "malas123"})
    assert resp.status_code == 429  # bloqueo temporal tras 5 intentos


def test_login_ok_y_logout(device_env):
    token = helpers.login_admin(client())
    c = client()
    resp = c.get("/api/people", headers=auth_header(token))
    assert resp.status_code == 200
    resp = c.post("/api/auth/logout", headers=auth_header(token))
    assert resp.status_code == 200
    resp = c.get("/api/people", headers=auth_header(token))
    assert resp.status_code == 401  # sesión terminada


# ---------------------------------------------------------------------- camera

def test_stream_camara_requiere_auth(device_env):
    resp = client().get("/api/camera/stream")
    assert resp.status_code == 401


def test_camera_desconectada(device_env):
    helpers.set_camera_disconnected()
    with pytest.raises(Exception) as exc_info:
        camera.get_source().read()
    assert "desconectada" in str(exc_info.value) or "disponible" in str(exc_info.value)


def test_device_status_con_camara_desconectada(device_env):
    helpers.set_camera_disconnected()
    token = helpers.login_admin(client())
    resp = client().get("/api/device/status", headers=auth_header(token))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["camera"]["available"] is False


# --------------------------------------------------------------------- personas

def test_crear_persona_validaciones(device_env):
    token = helpers.login_admin(client())
    c = client()
    resp = c.post("/api/people", headers=auth_header(token), json={})
    assert resp.status_code == 400
    resp = c.post("/api/people", headers=auth_header(token),
                  json={"full_name": "Fernanda Fuentes", "status": "hacked"})
    assert resp.status_code == 400
    resp = c.post("/api/people", headers=auth_header(token),
                  json={"full_name": "Fernanda Fuentes"})
    assert resp.status_code == 201


def test_suspend_revoke_activate(device_env):
    token = helpers.login_admin(client())
    c = client()
    pid = helpers.create_person("Gabriel G")
    assert db.query("SELECT status FROM people WHERE id=?", (pid,))[0]["status"] == "active"

    resp = c.post(f"/api/people/{pid}/suspend", headers=auth_header(token))
    assert resp.get_json()["status"] == "suspended"
    from device import access_service

    assert not access_service.decision_from_person(pid).granted

    resp = c.post(f"/api/people/{pid}/revoke", headers=auth_header(token))
    assert resp.get_json()["status"] == "revoked"
    assert not access_service.decision_from_person(pid).granted

    resp = c.post(f"/api/people/{pid}/activate", headers=auth_header(token))
    assert resp.get_json()["status"] == "active"
    assert access_service.decision_from_person(pid).granted


def test_capture_con_camara_desconectada(device_env):
    token = helpers.login_admin(client())
    pid = helpers.create_person("Héctor H")
    helpers.set_camera_disconnected()
    resp = client().post(f"/api/people/{pid}/capture",
                         headers=auth_header(token), json={"count": 3})
    assert resp.status_code == 503
    assert resp.get_json()["error"] == "camera_disconnected"


def test_capture_y_train_flujo_completo(device_env):
    """Flujo administrativo completo: registrar -> capturar (simulado) ->
    entrenar -> comprobar etiquetas -> activar permiso."""
    token = helpers.login_admin(client())
    c = client()
    resp = c.post("/api/people", headers=auth_header(token), json={"full_name": "Iris I"})
    pid = resp.get_json()["id"]

    # la captura con webcam real no es posible en CI: inyectamos imágenes
    profile = capture_service.ensure_face_profile(pid)
    helpers.add_face_images(pid, [5000, 5001, 5002])

    resp = c.post(f"/api/people/{pid}/train", headers=auth_header(token))
    assert resp.status_code == 201, resp.get_json()
    assert resp.get_json()["images_used"] == 3

    # etiquetas coherentes tras entrenar
    detail = c.get(f"/api/people/{pid}", headers=auth_header(token)).get_json()
    assert detail["face_profile"]["model_label"] == profile["model_label"]
    assert detail["roles"] == ["user"]


def test_delete_persona_borra_biometria(device_env):
    token = helpers.login_admin(client())
    pid = helpers.create_person("Jairo J")
    helpers.add_face_images(pid, [6000, 6001])
    resp = client().delete(f"/api/people/{pid}", headers=auth_header(token))
    assert resp.get_json()["face_images_deleted"] == 2
    assert not db.query("SELECT 1 FROM people WHERE id=?", (pid,))
    assert not db.query("SELECT 1 FROM face_profiles WHERE person_id=?", (pid,))
    assert not capture_service.list_saved_images(pid)


# -------------------------------------------------------------------- eventos

def test_acceso_registra_evento_y_event_id_unico(device_env):
    pid = helpers.create_person("Karla K")
    from device import access_service

    access_service.decision_from_person(pid)
    access_service.decision_from_person(pid)
    events = client().get(
        "/api/access-events?limit=10", headers=auth_header(helpers.login_admin(client()))
    ).get_json()
    assert len(events) >= 2
    ids = [e["event_id"] for e in events]
    assert len(ids) == len(set(ids))  # event_id únicos (dedup en sync)


# ---------------------------------------------------------------------- roles

def test_roles_endpoint(device_env):
    token = helpers.login_admin(client())
    c = client()
    roles = c.get("/api/roles", headers=auth_header(token)).get_json()
    names = {r["name"] for r in roles}
    assert {"admin", "user"}.issubset(names)
    # el rol user debe tener authorization access.granted; admin panel/admin
    per_user = {p for r in roles if r["name"] == "user" for p in r["permissions"]}
    assert "access.granted" in per_user
    per_admin = {p for r in roles if r["name"] == "admin" for p in r["permissions"]}
    assert {"access.granted", "panel.admin"}.issubset(per_admin)

    resp = c.post("/api/roles", headers=auth_header(token),
                  json={"name": "contractor", "description": "Contratista", "permissions": ["access.granted"]})
    assert resp.status_code == 201


# ---------------------------------------------------------------------- settings

def test_audit_log_registra_operaciones(device_env):
    token = helpers.login_admin(client())
    c = client()
    pid = c.post("/api/people", headers=auth_header(token),
                 json={"full_name": "Laura L"}).get_json()["id"]
    c.post(f"/api/people/{pid}/suspend", headers=auth_header(token))
    log = c.get("/api/audit-log", headers=auth_header(token)).get_json()
    actions = {row["action"] for row in log}
    assert {"person_create", "person_suspend", "login_ok"}.issubset(actions)
