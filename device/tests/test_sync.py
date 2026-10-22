"""Pruebas de sincronización: dedup por event_id, conflictos por versión,
revocación remota nunca reactivada por copia local obsoleta."""
from __future__ import annotations

import pytest

from device import config, db, event_service, sync_service
from . import helpers


def utc(offset_seconds: int) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)).isoformat(
        timespec="seconds"
    )


# -------------------------------------------------------------- eventos dedup

def _enable_sync(monkeypatch):
    monkeypatch.setattr(config, "SYNC_ENABLED", True)
    monkeypatch.setattr(config, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_SERVICE_ROLE_KEY", "test-key")


def test_eventos_pendientes_deduplicados(device_env, monkeypatch):
    _enable_sync(monkeypatch)
    pid = helpers.create_person("Miriam M")
    from device import access_service

    access_service.decision_from_person(pid)  # genera 1 evento
    first = event_service.pending_events()
    assert len(first) == 1

    pushed_payloads = []
    captured = {}

    def fake_request(method, path, payload=None):
        if path.startswith("/rest/v1/people"):
            return []
        if path.startswith("/rest/v1/access_events"):
            pushed_payloads.append(payload)
            return payload
        return []

    monkeypatch.setattr(sync_service, "_request", fake_request)
    result = sync_service.run_sync()
    assert result["status"] == "ok" and result["events_pushed"] == 1
    assert event_service.pending_events() == []

    # repetición del ciclo (simulando retransmisión tras caída): nada nuevo pendiente
    result2 = sync_service.run_sync()
    assert result2["events_pushed"] == 0
    ids = [e["event_id"] for payload in pushed_payloads for e in payload]
    assert len(ids) == len(set(ids))  # idempotencia: sin duplicados


# --------------------------------------------------- conflictos de personas

def test_revocacion_remota_mas_reciente_gana(device_env, monkeypatch):
    """La Pi sin conexión no puede reactivar un permiso revocado más recientemente."""
    pid = helpers.create_person("Nereo N", status="active")
    # antiguo local (updated_at viejo), remoto más nuevo con revoked
    db.execute("UPDATE people SET updated_at=? WHERE id=?", (utc(-100), pid))
    remote = [{
        "id": pid, "full_name": "Nereo N", "status": "revoked",
        "expires_at": None, "created_at": utc(-200), "updated_at": utc(-10),
    }]

    monkeypatch.setattr(sync_service, "_request", lambda m, p, payload=None: [])
    result = sync_service.merge_people(remote)
    assert "revoked" == db.query("SELECT status FROM people WHERE id=?", (pid,))[0]["status"]
    # la decisión inmediata con la política ya sincronizada debe ser denegada
    from device import access_service

    assert not access_service.decision_from_person(pid).granted


def test_local_mas_reciente_se_empuja(device_env, monkeypatch):
    pid = helpers.create_person("Omar O", status="suspended")
    remote_row = [{
        "id": pid, "full_name": "Omar O", "status": "active",
        "expires_at": None, "created_at": utc(-100), "updated_at": utc(-200),
    }]
    patches = []
    post_body = {}

    def fake_request(method, path, payload=None):
        if method == "GET":
            return remote_row
        if method == "PATCH":
            patches.append((path, payload))
            return {}
        if method == "POST":
            post_body.setdefault("people", []).append(payload)
            return {}
        return []

    monkeypatch.setattr(sync_service, "_request", fake_request)
    result = sync_service.merge_people(remote_row)
    # la persona local más reciente (suspended, updated_at nuevo) se empurja;
    # el remoto "active" viejo NO debe reactivarla
    assert "suspended" == db.query("SELECT status FROM people WHERE id=?", (pid,))[0]["status"]
    assert result["people_pushed"] >= 1


def test_empate_de_marcas_gana_estado_mas_estricto(device_env, monkeypatch):
    pid = helpers.create_person("Pilar P", status="active")
    stamp = utc(-5)
    db.execute("UPDATE people SET updated_at=? WHERE id=?", (stamp, pid))
    remote = [{
        "id": pid, "full_name": "Pilar P", "status": "suspended",
        "expires_at": None, "created_at": utc(-100), "updated_at": stamp,
    }]
    monkeypatch.setattr(sync_service, "_request", lambda m, p, payload=None: [])
    sync_service.merge_people(remote)
    assert db.query("SELECT status FROM people WHERE id=?", (pid,))[0]["status"] == "suspended"


def test_persona_nueva_en_remoto_se_copia(device_env, monkeypatch):
    rid = "11111111-1111-1111-1111-111111111111"
    remote = [{
        "id": rid, "full_name": "Quim Q", "status": "active",
        "expires_at": None, "created_at": utc(-20), "updated_at": utc(-20),
    }]
    monkeypatch.setattr(sync_service, "_request", lambda m, p, payload=None: [])
    sync_service.merge_people(remote)
    assert db.query("SELECT 1 FROM people WHERE id=?", (rid,))


# ------------------------------------------------- política vencida offline

def test_sync_offline_reporta_estado(device_env, monkeypatch):
    _enable_sync(monkeypatch)

    def fake_request(method, path, payload=None):
        raise ConnectionError("Sin conexión con Supabase")

    monkeypatch.setattr(sync_service, "_request", fake_request)
    result = sync_service.run_sync()
    assert result["status"] == "offline"
    # el sistema sigue reconociendo localmente (la decisión local no falla)
    pid = helpers.create_person("Rafa R")
    from device import access_service

    assert access_service.decision_from_person(pid).granted  # decisión local disponible


def test_marca_de_vigencia(device_env):
    assert sync_service.policy_sync_age_hours() is None
    db.set_setting("last_policy_sync", db.utcnow_iso())
    age = sync_service.policy_sync_age_hours()
    assert age is not None and age < 1
