"""Pruebas de la sesión de captura con retroalimentación (sin webcam real)."""
from __future__ import annotations

import time

import pytest

from device import capture_session, capture_service, config, db
from device.face_detector import FaceDetector
from . import helpers


def _wait_status(ses, statuses, timeout=20.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ses.snapshot()["status"] in statuses:
            return
        time.sleep(0.05)


def test_sesion_completa_contador_y_archivos(device_env, monkeypatch):
    monkeypatch.setattr(FaceDetector, "detect", lambda self, fr: [(50, 50, 150, 150)])
    helpers.set_camera_static([helpers.make_test_frame(9000)] * 50)
    monkeypatch.setattr(config, "CAPTURE_PACE_SECONDS", 0.02)
    pid = helpers.create_person("Dora D")
    ses = capture_session.start_session(pid, 5)
    _wait_status(ses, ("done",))
    snap = ses.snapshot()
    assert snap["status"] == "done", snap
    assert snap["saved"] == 5 and snap["target"] == 5
    assert "Completado" in snap["guidance"]
    assert len(capture_service.list_saved_images(pid)) == 5
    # preview disponible (fuente MJPEG del panel)
    assert isinstance(ses.read_preview(), bytes)
    # registro en auditoría
    auds = [row["action"] for row in db.query("SELECT action FROM audit_log")]
    assert "faces_capture_done" in auds


def test_guia_sin_rostro(device_env, monkeypatch):
    monkeypatch.setattr(FaceDetector, "detect", lambda self, fr: [])
    helpers.set_camera_static([helpers.make_test_frame(9100)] * 10)
    monkeypatch.setattr(config, "CAPTURE_PACE_SECONDS", 0.02)
    pid = helpers.create_person("Elsa E")
    ses = capture_session.start_session(pid, 3)
    time.sleep(0.3)
    snap = ses.snapshot()
    assert snap["saved"] == 0
    assert "rostro" in snap["guidance"].lower()
    ses.request_stop()
    _wait_status(ses, ("cancelled",))


def test_sesion_unica_y_detencion(device_env, monkeypatch):
    monkeypatch.setattr(FaceDetector, "detect", lambda self, fr: [])
    helpers.set_camera_static([helpers.make_test_frame(9300)] * 20)
    monkeypatch.setattr(config, "CAPTURE_PACE_SECONDS", 0.5)
    pid = helpers.create_person("Gina G")
    ses = capture_session.start_session(pid, 30)
    with pytest.raises(capture_session.CaptureBusyError):
        capture_session.start_session(pid, 5)
    ses.request_stop()
    _wait_status(ses, ("cancelled",))
    assert capture_session.get_session(ses.id) is ses
    # expiración del registro vacía sesiones terminadas
    ses2 = capture_session.start_session(pid, 3)
    assert ses2.id != ses.id
    ses2.request_stop()
