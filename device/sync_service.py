"""Sincronización con Supabase (opcional): sube eventos pendientes, empuja
cambios de personas/roles y descarga políticas actualizadas.

Reglas de conflicto:
- Nunca se baja un cambio anterior a uno local más reciente (last-writer-wins
  por updated_at en UTC).
- Si el conflicto es de estado y las marcas empatan, gana el estado más
  estricto: revoked > suspended > active. Así una copia local obsoleta NUNCA
  reactiva un permiso revocado más recientemente.
- Los access_events son idempotentes por event_id (upsert on_conflict).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import config, db, event_service

_STRICTNESS = {"active": 0, "suspended": 1, "revoked": 2}


class SyncResult(dict):
    pass


def _headers() -> dict:
    return {
        "apikey": config.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {config.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


def _request(method: str, path: str, payload=None) -> list | dict:
    url = f"{config.SUPABASE_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode() or "[]"
            return json.loads(body)
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Sin conexión con Supabase: {exc}") from exc


def _stricter_status(a: str, b: str) -> str:
    return a if _STRICTNESS.get(a, 0) >= _STRICTNESS.get(b, 0) else b


def _first_updated(d: dict) -> str:
    return d.get("updated_at") or d.get("created_at") or ""


def merge_people(remote: list[dict]) -> dict:
    """Aplica políticas remotas a la base local con las reglas anteriores."""
    pushed, pulled, conflicts = 0, 0, 0
    local_rows = {r["id"]: dict(r) for r in db.query("SELECT * FROM people")}
    remote_by_id = {r["id"]: r for r in remote}

    # 1) Empujar personas locales modificadas después del último pull.
    for pid, local in local_rows.items():
        remote_row = remote_by_id.get(pid)
        if remote_row is None:
            body = {k: local[k] for k in ("id", "full_name", "document_id", "status", "expires_at", "created_at", "updated_at")}
            _request("POST", "/rest/v1/people", body)
            pushed += 1
            continue
        l_up = local["updated_at"] or ""
        r_up = remote_row.get("updated_at") or ""
        if l_up > r_up:
            body = {k: local[k] for k in ("full_name", "status", "expires_at", "updated_at")}
            _request("PATCH", f"/rest/v1/people?id=eq.{pid}", body)
            pushed += 1
        elif r_up > l_up:
            merged_status = remote_row["status"]
            db.execute(
                "UPDATE people SET full_name=?, status=?, expires_at=?, updated_at=? WHERE id=?",
                (remote_row["full_name"], remote_row["status"], remote_row["expires_at"], remote_row["updated_at"], pid),
            )
            pulled += 1
        elif remote_row["status"] != local["status"]:
            merged = _stricter_status(remote_row["status"], local["status"])
            merged_updated = max(remote_row.get("updated_at") or "", local["updated_at"] or "")
            db.execute("UPDATE people SET status=?, updated_at=? WHERE id=?", (merged, merged_updated, pid))
            conflicts += 1

    # 2) Personas nuevas en remoto.
    for rid, remote_row in remote_by_id.items():
        if rid not in local_rows:
            db.execute(
                "INSERT OR IGNORE INTO people (id, full_name, document_id, status, expires_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    remote_row["id"], remote_row["full_name"], remote_row.get("document_id"),
                    remote_row["status"], remote_row.get("expires_at"), remote_row.get("created_at"),
                    remote_row.get("updated_at"),
                ),
            )
            pulled += 1
    return {"people_pushed": pushed, "people_pulled": pulled, "conflicts": conflicts}


def _sync_events() -> dict:
    pushed = 0
    events = event_service.pending_events()
    if events:
        _request("POST", "/rest/v1/access_events", events)
        event_service.mark_synced([e["event_id"] for e in events])
        pushed = len(events)
    return {"events_pushed": pushed}


def run_sync() -> SyncResult:
    if not (config.SYNC_ENABLED and config.SUPABASE_URL and config.SUPABASE_SERVICE_ROLE_KEY):
        raise ConnectionError("Sincronización deshabilitada o sin credenciales")
    result: SyncResult = SyncResult()
    try:
        remote_people = _request("GET", "/rest/v1/people?select=*", None)
        result.update(merge_people(remote_people))
        result.update(_sync_events())
        db.set_setting("last_policy_sync", db.utcnow_iso())
        result["status"] = "ok"
    except ConnectionError as exc:
        result["status"] = "offline"
        result["error"] = str(exc)
    return result


def policy_sync_age_hours() -> float | None:
    last = db.get_setting("last_policy_sync")
    if not last:
        return None
    try:
        dt = datetime.fromisoformat(last)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
