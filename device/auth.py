"""Autenticación administrativa local.

- Hash PBKDF2-SHA256 (300k iteraciones contra la librería probada hashlib).
- Tokens de sesión opacos en memoria con TTL.
- Rate-limit de login por usuario+IP (lockout temporal).
- Las credenciales NO llegan por el navegador: la cuenta se crea con el CLI
  (`python -m device.cli init-admin`).
El rol de administrador NUNCA se deriva del reconocimiento facial.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from . import db, config

SESSIONS: dict[str, dict] = {}
_session_lock = threading.Lock()
_attempts: dict[str, list[float]] = {}
_attempt_lock = threading.Lock()

PBKDF2_ITERATIONS = 300_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2:sha256:{PBKDF2_ITERATIONS}:{salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, algo, iters, salt_hex, digest_hex = stored.split(":")
        if scheme != "pbkdf2" or algo != "sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, AttributeError):
        return False


def init_admin(username: str, password: str, full_name: str = "Administrador") -> None:
    """Crea el primer administrador: SOLO procedimiento de inicialización seguro (CLI)."""
    if not username or len(password) < 10:
        raise ValueError("La contraseña debe tener al menos 10 caracteres")
    existing = db.query("SELECT id FROM admin_accounts WHERE role='admin' AND enabled=1")
    admin_id = str(existing[0]["id"]) if existing else secrets.token_hex(16)
    db.execute(
        "INSERT INTO admin_accounts (id, username, password_hash, full_name, role, enabled, created_at) "
        "VALUES (?, ?, ?, ?, 'admin', 1, ?) "
        "ON CONFLICT(id) DO UPDATE SET password_hash=excluded.password_hash, "
        "username=excluded.username, full_name=excluded.full_name",
        (admin_id, username, hash_password(password), full_name, db.utcnow_iso()),
    )
    db.execute(
        "INSERT INTO audit_log (action, actor, detail, timestamp) VALUES (?, ?, ?, ?)",
        ("init_admin", "cli", f"admin creada/actualizada: {username}", db.utcnow_iso()),
    )


def _attempt_key(username: str, ip: str) -> str:
    return f"{username}|{ip}"


def _is_locked(key: str) -> float:
    """Devuelve segundos restantes de lockout; 0 si está desbloqueado."""
    now = time.time()
    with _attempt_lock:
        attempts = [t for t in _attempts.get(key, []) if now - t < config.LOGIN_LOCKOUT_SECONDS]
        _attempts[key] = attempts
        if len(attempts) >= config.LOGIN_MAX_ATTEMPTS:
            return max(0.0, config.LOGIN_LOCKOUT_SECONDS - (now - attempts[0]))
    return 0.0


def record_attempt(key: str) -> None:
    with _attempt_lock:
        _attempts.setdefault(key, []).append(time.time())


def _clear_attempts(key: str) -> None:
    with _attempt_lock:
        _attempts.pop(key, None)


def login(username: str, password: str, ip: str = "-") -> dict | None:
    """Devuelve el token de sesión o None si falla (con rate limiting)."""
    key = _attempt_key(username, ip)
    wait = _is_locked(key)
    if wait > 0:
        raise PermissionError(f"Demasiados intentos; reintenta en {math.ceil(wait)}s")
    rows = db.query(
        "SELECT * FROM admin_accounts WHERE username = ? AND enabled = 1 AND role = 'admin'",
        (username,),
    )
    if not rows or not verify_password(password, rows[0]["password_hash"]):
        record_attempt(key)
        db.execute(
            "INSERT INTO audit_log (action, actor, detail, timestamp) VALUES (?, ?, ?, ?)",
            ("login_failed", username, f"ip={ip}", db.utcnow_iso()),
        )
        return None
    _clear_attempts(key)
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(seconds=config.SESSION_TTL_SECONDS)
    with _session_lock:
        SESSIONS[token] = {
            "username": username,
            "role": "admin",
            "expires": expires,
        }
    db.execute(
        "INSERT INTO audit_log (action, actor, detail, timestamp) VALUES (?, ?, ?, ?)",
        ("login_ok", username, f"ip={ip}", db.utcnow_iso()),
    )
    return {"token": token, "username": username, "expires": expires.isoformat()}


def verify_session(token: str | None) -> dict | None:
    if not token:
        return None
    with _session_lock:
        info = SESSIONS.get(token)
        if not info:
            return None
        if datetime.now(timezone.utc) >= info["expires"]:
            SESSIONS.pop(token, None)
            return None
        return info


def logout(token: str | None) -> None:
    if token:
        with _session_lock:
            SESSIONS.pop(token, None)


require = verify_session  # alias semántico
