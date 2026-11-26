"""Pruebas de regresión de la revisión de seguridad (rama fix/revision-seguridad)."""
from __future__ import annotations

import numpy as np

from device import access_service, auth, config, db
from device.app import app
from device.face_recognizer import crop_face, get_recognizer, invalidate_shared, next_model_label
from . import helpers


def client():
    app.config["TESTING"] = True
    return app.test_client()


def H(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------ 1. etiquetas no reutilizadas

def test_etiqueta_de_persona_borrada_no_se_reutiliza(device_env):
    a = helpers.create_person("Ana Uno")
    helpers.add_face_images(a, [1, 2, 3])
    b = helpers.create_person("Beto Dos")
    helpers.add_face_images(b, [100, 101, 102])
    label_b = db.query("SELECT model_label FROM face_profiles WHERE person_id=?", (b,))[0]["model_label"]

    token = helpers.login_admin(client())
    resp = client().delete(f"/api/people/{b}", headers=H(token))
    assert resp.status_code == 200

    assert next_model_label() > label_b  # nunca vuelve a salir la etiqueta de Beto


def test_borrar_persona_reentrena_y_su_rostro_ya_no_entra(device_env):
    a = helpers.create_person("Ana Uno")
    helpers.add_face_images(a, [1, 2, 3])
    b = helpers.create_person("Beto Dos")
    helpers.add_face_images(b, [100, 101, 102])
    get_recognizer().train()
    invalidate_shared()

    token = helpers.login_admin(client())
    resp = client().delete(f"/api/people/{b}", headers=H(token))
    assert resp.get_json()["model_retrained"] is True

    # Persona nueva registrada DESPUÉS del borrado, sin reentrenar todavía
    c = helpers.create_person("Carla Tres")
    helpers.add_face_images(c, [500, 501, 502])
    invalidate_shared()

    from device.face_recognizer import load_face_to_train
    rostro_beto = load_face_to_train(helpers.make_face_image(100))
    decision = access_service.decide_from_recognition(get_recognizer().predict(rostro_beto), log=False)
    assert not (decision.granted and decision.person_id == c)


def test_primera_etiqueta_sigue_siendo_1(device_env):
    assert next_model_label() == 1  # compatibilidad con el modelo base


# ------------------------------------------------------- 2. mismo recorte

def test_crop_face_aplica_margen_y_respeta_bordes():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    roi = crop_face(frame, (100, 100, 200, 200))
    m = int(200 * config.FACE_MARGIN)
    assert roi.shape[:2] == (200 + 2 * m, 200 + 2 * m)
    roi_borde = crop_face(frame, (0, 0, 100, 100))
    assert roi_borde.shape[:2] == (100 + int(100 * config.FACE_MARGIN),) * 2


# -------------------------------------------- 3. rate limit no se salta con XFF

def test_rate_limit_no_se_salta_cambiando_x_forwarded_for(device_env):
    auth.init_admin("admin", "Sup3rSecret!234")
    c = client()
    for i in range(6):
        resp = c.post(
            "/api/auth/login",
            json={"username": "admin", "password": "malas123"},
            headers={"X-Forwarded-For": f"10.0.0.{i}"},
        )
    assert resp.status_code == 429


# ----------------------------------------------- 4. PATCH solo con roles

def test_patch_solo_roles_funciona(device_env):
    pid = helpers.create_person("Ana Uno", roles=("user",))
    token = helpers.login_admin(client())
    c = client()
    resp = c.patch(f"/api/people/{pid}", json={"roles": ["admin", "user"]}, headers=H(token))
    assert resp.status_code == 200, resp.get_json()
    roles = c.get(f"/api/people/{pid}", headers=H(token)).get_json()["roles"]
    assert sorted(roles) == ["admin", "user"]


def test_patch_roles_no_lista_es_400(device_env):
    pid = helpers.create_person("Ana Uno")
    token = helpers.login_admin(client())
    resp = client().patch(f"/api/people/{pid}", json={"roles": "admin"}, headers=H(token))
    assert resp.status_code == 400


# ------------------------------------------------- 5. errores 400/503, no 500

def test_parametros_no_numericos_dan_400(device_env):
    pid = helpers.create_person("Ana Uno")
    token = helpers.login_admin(client())
    c = client()
    assert c.get("/api/access-events?limit=abc", headers=H(token)).status_code == 400
    assert c.post(f"/api/people/{pid}/capture", json={"count": "x"}, headers=H(token)).status_code == 400
    assert c.post(f"/api/people/{pid}/capture-session", json={"count": "x"}, headers=H(token)).status_code == 400


def test_stream_token_sin_camara_da_503(device_env):
    helpers.set_camera_disconnected()
    token = helpers.login_admin(client())
    resp = client().post("/api/camera/stream-token", headers=H(token))
    assert resp.status_code == 503


# ------------------------------------------------ 6. settings protegidas

def test_settings_protegidas_no_editables(device_env):
    token = helpers.login_admin(client())
    resp = client().patch("/api/settings", json={"last_policy_sync": "2099-01-01T00:00:00+00:00"},
                          headers=H(token))
    assert resp.status_code == 400
    assert db.get_setting("last_policy_sync") is None
