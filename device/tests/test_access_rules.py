"""Pruebas de las reglas de autorización (sin webcam)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from device import access_service, db, event_service
from device.face_recognizer import MatchResult

from . import helpers


def make_match(label=None, distance=20.0, accepted=None):
    if accepted is None:
        accepted = label is not None
    return MatchResult(label=label, distance=distance, accepted=accepted)


# ------------------------------------------------------- persona autorizada

def test_persona_autorizada(device_env):
    pid = helpers.create_person("Carlos Pérez", roles=("user",))
    decision = access_service.decision_from_person(pid)
    assert decision.granted
    assert decision.category == "welcome"
    assert decision.display_name == "Carlos"
    events = event_service.recent(5)
    assert events[0]["result"] == "granted"


def test_desconocida_no_recibe_permisos(device_env):
    decision = access_service.decide_from_recognition(make_match(None, 120.0, accepted=False))
    assert not decision.granted and decision.category == "denied_unknown"
    decision2 = access_service.decision_from_person(None)
    assert not decision2.granted and decision2.category == "denied_unknown"


def test_persona_suspendida(device_env):
    pid = helpers.create_person("Ana Suspendida", status="suspended")
    decision = access_service.decision_from_person(pid)
    assert not decision.granted and decision.category == "denied_suspended"


def test_persona_revocada_y_recomprobacion_inmediata(device_env):
    pid = helpers.create_person("Luis Revocado")
    assert access_service.decision_from_person(pid).granted
    db.execute("UPDATE people SET status='revoked', updated_at=? WHERE id=?",
               (db.utcnow_iso(), pid))
    decision = access_service.decision_from_person(pid)
    assert not decision.granted and decision.category == "denied_revoked"


def test_permiso_vencido(device_env):
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    pid = helpers.create_person("Rosa Vencida", expires_at=expired)
    decision = access_service.decision_from_person(pid)
    assert not decision.granted and decision.category == "denied_expired"


def test_permiso_vigente_no_vencido(device_env):
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    pid = helpers.create_person("Marcos Vigente", expires_at=future)
    assert access_service.decision_from_person(pid).granted


def test_usuario_sin_rol(device_env):
    pid = helpers.create_person("Nadia SinRol", roles=())
    decision = access_service.decision_from_person(pid)
    assert not decision.granted and decision.category == "denied_no_role"


def test_rol_sin_permiso_granted(device_env):
    # rol nuevo sin el permiso access.granted: no da acceso aunque esté asignado
    db.execute("INSERT OR IGNORE INTO roles (id,name) VALUES (9,'visitante')")
    pid = helpers.create_person("Pablo Visitante", roles=("visitante",))
    decision = access_service.decision_from_person(pid)
    assert not decision.granted and decision.category == "denied_no_role"


def test_etiqueta_inconsistente_nunca_grant(device_env):
    # accepted pero la etiqueta no existe en face_profiles activos
    m = make_match(label=999, distance=10.0, accepted=True)
    decision = access_service.evaluate_identity(m)
    assert not decision.granted and decision.category == "denied_wrong_label"


def test_reconocer_cara_no_da_rol_admin(device_env):
    # persona autorizada como user: solo welcome; el rol admin no se deriva de la cara
    from device import capture_service

    pid = helpers.create_person("Elena Usuario", roles=("user",))
    label = capture_service.ensure_face_profile(pid)["model_label"]
    decision = access_service.decide_from_recognition(make_match(label, 15.0))
    assert decision.granted and decision.category == "welcome"
    roles = db.query("SELECT name FROM roles r JOIN person_roles pr ON pr.role_id=r.id "
                     "WHERE pr.person_id=?", (pid,))
    assert [r["name"] for r in roles] == ["user"]


# --------------------------------------------------------- política remota

def test_politica_local_vencida_denegada_con_sync_activado(device_env, monkeypatch):
    monkeypatch.setenv("SYNC_ENABLED", "true")
    pid = helpers.create_person("Elias Bloqueado")
    decision = access_service.decision_from_person(pid)
    assert not decision.granted and decision.category == "denied_internal_error"
    # y se registra el error
    events = event_service.recent(1)
    assert events[0]["category"] == "denied_internal_error"


def test_politica_vigente_con_last_policy_sync(device_env):
    pid = helpers.create_person("Firma Vigente")
    db.set_setting("last_policy_sync", db.utcnow_iso())
    assert access_service.decision_from_person(pid).granted


def test_decision_nunca_grant_en_error_interno(device_env, monkeypatch):
    from device import access_service as a

    pid = helpers.create_person("Zoe Error")
    monkeypatch.setattr(a, "_role_has_access", lambda pid: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        a.decision_from_person(pid)
    # en producción, el flujo HTTP captura y registra denied_internal_error
    a._log_decision(a.AccessDecision(False, "denied_internal_error", pid, None, "ZeroDivisionError", None))
    events = event_service.recent(1)
    assert events[0]["result"] == "denied"
    assert events[0]["category"] == "denied_internal_error"
