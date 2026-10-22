"""Pruebas del reconocedor LBPH (entrenamiento/predicción sin webcam)."""
from __future__ import annotations

import pytest

from device import db, capture_service
from device.face_recognizer import LBPHRecognizer, ModelUnavailableError, next_model_label
from . import helpers


def test_etiquetas_unicas_incrementales(device_env):
    a = helpers.create_person("Ana")
    b = helpers.create_person("Bruno")
    profile_a = capture_service.ensure_face_profile(a)["model_label"]
    profile_b = capture_service.ensure_face_profile(b)["model_label"]
    assert profile_b == profile_a + 1
    labels = [int(r["model_label"]) for r in db.query("SELECT model_label FROM face_profiles")]
    assert len(labels) == len(set(labels))  # no duplicadas


def test_modelo_inexistente_raises(device_env):
    rec = LBPHRecognizer()
    with pytest.raises(ModelUnavailableError):
        rec.load()


def test_entrenamiento_y_reconocimiento(device_env):
    pid_a = helpers.create_person("Cristina A")
    pid_b = helpers.create_person("Diego B")
    pa = capture_service.ensure_face_profile(pid_a)
    pb = capture_service.ensure_face_profile(pid_b)
    helpers.add_face_images(pid_a, [1000, 1001, 1002])
    helpers.add_face_images(pid_b, [2000, 2001, 2002])
    rec = LBPHRecognizer()
    used = rec.train()
    assert used == 6

    # persona A conocida: distancia ~0 para la misma imagen de entrenamiento
    match_a = rec.predict(helpers.make_face_image(1000))
    assert match_a.accepted and match_a.label == pa["model_label"]

    # rostro ajeno, fuera del umbral: NO concede identidad
    stranger = rec.predict(helpers.make_face_image(777777))
    assert not stranger.accepted


def test_prediccion_sin_entrenar_raises(device_env):
    rec = LBPHRecognizer()
    with pytest.raises(ModelUnavailableError):
        rec.predict(helpers.make_face_image(3))


def test_entrenar_sin_imagenes_queda_invalido(device_env):
    pid = helpers.create_person("Sin Imágenes")
    capture_service.ensure_face_profile(pid)
    rec = LBPHRecognizer()
    with pytest.raises(ModelUnavailableError):
        rec.train()
    assert not rec.model_path.exists()


def test_perfil_desactivado_excluido(device_env):
    pid = helpers.create_person("Erick Desactivado")
    capture_service.ensure_face_profile(pid)
    helpers.add_face_images(pid, [3000, 3001, 3002, 3003])
    db.execute("UPDATE face_profiles SET enabled=0 WHERE person_id=?", (pid,))
    rec = LBPHRecognizer()
    with pytest.raises(ModelUnavailableError):
        rec.train()
