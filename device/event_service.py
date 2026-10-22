"""Registro de eventos de acceso, con event_id único y cola de sincronización."""
from __future__ import annotations

import uuid

from . import db, config


def log_access(
    *,
    person_id: str | None,
    result: str,
    reason: str,
    category: str | None,
    confidence: float | None = None,
    timestamp: str | None = None,
) -> str:
    """Registra un intento. SIEMPRE con event_id UUID v4 propio para que la
    sincronización pueda deduplicar. Devuelve el event_id."""
    event_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO access_events "
        "(event_id, person_id, device_id, result, reason, category, timestamp, confidence, synced) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
        (
            event_id,
            person_id,
            config.device_id(),
            result,
            reason,
            category,
            timestamp or db.utcnow_iso(),
            confidence,
        ),
    )
    return event_id


def pending_events(limit: int = 200) -> list[dict]:
    rows = db.query(
        "SELECT event_id, person_id, device_id, result, reason, category, timestamp, confidence "
        "FROM access_events WHERE synced = 0 ORDER BY id LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


def mark_synced(event_ids: list[str]) -> None:
    if not event_ids:
        return
    qmarks = ",".join("?" for _ in event_ids)
    db.execute(f"UPDATE access_events SET synced = 1 WHERE event_id IN ({qmarks})", tuple(event_ids))


def recent(limit: int = 20) -> list[dict]:
    rows = db.query(
        "SELECT e.event_id, e.person_id, e.result, e.reason, e.category, e.timestamp, e.confidence, "
        "p.full_name FROM access_events e LEFT JOIN people p ON p.id = e.person_id "
        "ORDER BY e.id DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in rows]


def summary() -> dict:
    total = db.query("SELECT COUNT(*) AS c FROM access_events")[0]["c"]
    granted = db.query("SELECT COUNT(*) AS c FROM access_events WHERE result='granted'")[0]["c"]
    denied = db.query("SELECT COUNT(*) AS c FROM access_events WHERE result='denied'")[0]["c"]
    unsynced = db.query("SELECT COUNT(*) AS c FROM access_events WHERE synced=0")[0]["c"]
    return {"total": total, "granted": granted, "denied": denied, "unsynced": unsynced}
