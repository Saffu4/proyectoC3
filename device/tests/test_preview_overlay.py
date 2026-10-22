"""Pruebas de la vista con reconocimiento en vivo (preview_overlay).

Verifican que la anotación refleja la MISMA decisión que el acceso real
(welcome/denied por estado), que no escribe eventos (solo informativa) y
que sin modelo entrenado muestra un indicador explícito."""
from __future__ import annotations

import cv2

from device import db, preview_overlay
from device.face_recognizer import get_recognizer

from . import helpers


def _rect(frame):
    h, w = frame.shape[:2]
    return [(0, 0, w, h)]


def test_conocido_con_acceso_muestra_verde_y_nombre(device_env):
    pid = helpers.create_person("Carlos Gomez")
    helpers.add_face_images(pid, [1000, 1001, 1002, 1003, 1004])
    assert get_recognizer().train() == 5

    frame = helpers.make_face_image(1000)  # semilla entrenada
    annotated, results = preview_overlay.annotate_frame(frame, _rect(frame), get_recognizer())

    assert len(results) == 1
    r = results[0]
    assert r["category"] == "welcome"
    assert r["display_name"] == "Carlos"
    assert isinstance(annotated, cv2.typing.MatLike if hasattr(cv2, "typing") else object)
    assert annotated.shape == frame.shape


def test_desconocido_muestra_rojo(device_env):
    pid = helpers.create_person("Ana Perez")
    helpers.add_face_images(pid, [1000, 1001, 1002, 1003, 1004])
    get_recognizer().train()

    frame = helpers.make_face_image(777777)
    annotated, results = preview_overlay.annotate_frame(frame, _rect(frame), get_recognizer())
    assert results[0]["category"] == "denied_unknown"
    assert results[0]["display_name"] is None


def test_suspendido_muestra_estado(device_env):
    pid = helpers.create_person("Luis Rojo", status="suspended")
    helpers.add_face_images(pid, [2000, 2001, 2002, 2003, 2004])
    get_recognizer().train()

    frame = helpers.make_face_image(2000)
    _a, results = preview_overlay.annotate_frame(frame, _rect(frame), get_recognizer())
    assert results[0]["category"] == "denied_suspended"


def test_sin_modelo_indica_explícito(device_env):
    # persona registrada pero ningún train() ejecutado
    pid = helpers.create_person("Marta Sin")
    helpers.add_face_images(pid, [3000, 3001, 3002, 3003, 3004])

    frame = helpers.make_face_image(3000)
    _a, results = preview_overlay.annotate_frame(frame, _rect(frame), get_recognizer())
    assert results[0]["category"] == "denied_model"


def test_la_vista_no_registra_eventos(device_env):
    pid = helpers.create_person("Noe Log")
    helpers.add_face_images(pid, [4000, 4001, 4002, 4003, 4004])
    get_recognizer().train()

    frame = helpers.make_face_image(4000)
    preview_overlay.annotate_frame(frame, _rect(frame), get_recognizer())

    assert db.query("SELECT COUNT(*) AS n FROM access_events")[0]["n"] == 0
    assert db.query("SELECT COUNT(*) AS n FROM audit_log")[0]["n"] == 0
