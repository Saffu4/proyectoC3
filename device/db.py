"""SQLite: esquema y helpers. Única fuente de verdad local del dispositivo."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS people (
  id TEXT PRIMARY KEY,
  full_name TEXT NOT NULL,
  document_id TEXT,
  status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active','suspended','revoked')),
  expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE IF NOT EXISTS person_roles (
  person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  PRIMARY KEY (person_id, role_id)
);

CREATE TABLE IF NOT EXISTS permissions (
  id INTEGER PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE IF NOT EXISTS role_permissions (
  role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id INTEGER NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE IF NOT EXISTS face_profiles (
  id TEXT PRIMARY KEY,
  person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
  -- model_label es la etiqueta LBPH. Es ÚNICA y solo la gestiona este módulo.
  model_label INTEGER NOT NULL UNIQUE,
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS access_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id TEXT NOT NULL UNIQUE,          -- evita duplicados en sincronización
  person_id TEXT REFERENCES people(id) ON DELETE SET NULL,
  device_id TEXT NOT NULL,
  result TEXT NOT NULL CHECK (result IN ('granted','denied')),
  reason TEXT NOT NULL,
  -- categories: unknown / suspended / revoked / expired / no_role /
  --             unknown_label / invalid_confidence / internal_error / (null si granted)
  category TEXT,
  timestamp TEXT NOT NULL,
  confidence REAL,                        -- distancia LBPH; NO es probabilidad
  synced INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_events_time ON access_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_events_sync ON access_events(synced);

CREATE TABLE IF NOT EXISTS admin_accounts (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,            -- PBKDF2-SHA256
  full_name TEXT,
  role TEXT NOT NULL DEFAULT 'admin',
  enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT NOT NULL,
  actor TEXT NOT NULL,
  detail TEXT,
  timestamp TEXT NOT NULL
);
"""

_conn_lock = threading.Lock()
_init_done = False


def _connect() -> sqlite3.Connection:
    config.ensure_data_dirs()
    db_path = config.data_dir() / "proyecto_c3.sqlite"
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    global _init_done
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        # Roles y permisos iniciales (idempotente)
        conn.execute(
            "INSERT OR IGNORE INTO roles (id, name, description) VALUES (1, 'admin', 'Acceso administrativo total')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO roles (id, name, description) VALUES (2, 'user', 'Acceso autorizado estándar')"
        )
        codes = [
            ("access.granted", "Puede pasar por el punto de acceso"),
            ("panel.admin", "Acceso al panel de administración"),
        ]
        for code, desc in codes:
            conn.execute(
                "INSERT OR IGNORE INTO permissions (code, description) VALUES (?, ?)", (code, desc)
            )
        # admin quiere ambos permisos; user solo access.granted
        conn.execute(
            "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) "
            "SELECT 1, id FROM permissions WHERE code IN ('access.granted','panel.admin')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO role_permissions (role_id, permission_id) "
            "SELECT 2, id FROM permissions WHERE code = 'access.granted'"
        )
        conn.commit()
    with _conn_lock:
        _init_done = True


@contextmanager
def get_conn():
    with _conn_lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def query(sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def execute(sql: str, params: tuple = ()) -> int:
    with get_conn() as conn:
        cur = conn.execute(sql, params)
        return cur.rowcount


def get_setting(key: str, default: str | None = None) -> str | None:
    rows = query("SELECT value FROM settings WHERE key = ?", (key,))
    return rows[0]["value"] if rows else default


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
