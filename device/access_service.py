"""Servicio central de autorización. Toda decisión pasa por aquí.

Reglas (resumen):
- Desconocido, suspendido, revocado, vencido o sin rol con permiso de acceso
  nunca obtiene permiso concedido ni categorías de redirección privilegiadas.
- La distancia LBPH NO es probabilidad: se compara contra un umbral calibrado.
- Fallo interno / modelo inválido => deny e internal_error, nunca grant.
- Reconocer un rostro jamás otorga rol administrativo.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from . import db, event_service
from .face_recognizer import MatchResult, ModelUnavailableError

ACCESS_PERMISSION_CODE = "access.granted"


@dataclass
class AccessDecision:
    granted: bool
    category: str  # welcome | denied_unknown | denied_suspended | denied_revoked |
                   # denied_expired | denied_no_role | denied_wrong_label | denied_model |
                   # denied_camera | denied_db | denied_error
    person_id: str | None
    display_name: str | None  # solo primer nombre; jamás datos administrativos
    reason: str
    confidence: float | None  # distancia LBPH cruda (calibración), no probabilidad


def _policy_is_fresh() -> tuple[bool, str]:
    """Comprueba vigencia de la copia local de políticas en modo 'estricto'."""
    import os

    from . import config

    max_age = float(os.environ.get("POLICY_MAX_AGE_HOURS", str(config.POLICY_MAX_AGE_HOURS)))
    last = db.get_setting("last_policy_sync")
    if not last:
        # Sin sincronización configurada: la política local se considera válida
        # mientras el administrador no active el modo estricto.
        if os.environ.get("SYNC_ENABLED", "").lower() == "true":
            return False, "Política local sin copia remota y sincronización activada"
        return True, "sin sincronización configurada"
    try:
        dt = datetime.fromisoformat(last)
    except ValueError:
        return False, "Marca de última sincronización inválida"
    elapsed_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
    if elapsed_h > max_age:
        return False, f"Copia de política vencida ({elapsed_h:.1f}h > {max_age:.1f}h)"
    return True, "vigente"


def _role_has_access(person_id: str) -> bool:
    rows = db.query(
        """
        SELECT 1 FROM person_roles pr
        JOIN role_permissions rp ON rp.role_id = pr.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE pr.person_id = ? AND p.code = ?
        LIMIT 1
        """,
        (person_id, ACCESS_PERMISSION_CODE),
    )
    return bool(rows)


def decision_from_person(person_id: str | None, *, distance: float | None = None,
                         log: bool = True) -> AccessDecision:
    """Evalúa el estado completo de una persona ya identificada por su id.
    Registra el resultado por defecto (punto único de registro de eventos)."""
    decision = _evaluate_person_state(person_id, distance=distance)
    if log:
        _log_decision(decision)
    return decision


def _evaluate_person_state(person_id: str | None, *, distance: float | None = None) -> AccessDecision:
    if person_id is None:
        return AccessDecision(False, "denied_unknown", None, None, "Rostro no reconocido", distance)
    fresh, detail = _policy_is_fresh()
    if not fresh:
        return AccessDecision(
            False, "denied_internal_error", person_id, None, f"Política local {detail}", distance
        )
    rows = db.query(
        "SELECT full_name, status, expires_at FROM people WHERE id = ?", (person_id,)
    )
    if not rows:
        # El perfil existe pero la persona fue borrada: etiqueta huérfana.
        return AccessDecision(
            False, "denied_unknown", person_id, None, "Etiqueta sin persona asociada", distance
        )
    p = rows[0]
    if p["status"] == "revoked":
        return AccessDecision(False, "denied_revoked", person_id, None, "Permiso revocado", distance)
    if p["status"] == "suspended":
        return AccessDecision(False, "denied_suspended", person_id, None, "Persona suspendida", distance)
    if p["expires_at"]:
        try:
            exp = datetime.fromisoformat(str(p["expires_at"]))
        except ValueError:
            return AccessDecision(
                False, "denied_internal_error", person_id, None, "Fecha de vencimiento inválida", distance
            )
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= datetime.now(timezone.utc):
            return AccessDecision(False, "denied_expired", person_id, None, "Permiso vencido", distance)
    if not _role_has_access(person_id):
        return AccessDecision(False, "denied_no_role", person_id, None, "Sin rol con permiso de acceso", distance)
    first = str(p["full_name"]).split(" ")[0]
    return AccessDecision(True, "welcome", person_id, first, "Autorización vigente", distance)


def evaluate_identity(match: MatchResult) -> AccessDecision:
    """Convierte un resultado del reconocedor en una decisión completa."""
    if not match.accepted or match.label is None:
        reason = (
            f"Coincidencia fuera del umbral (dist={match.distance:.1f})" if match.distance is not None
            else "Etiqueta no reconocida"
        )
        if match.label is not None and match.accepted:
            # accepted=True pero label inválida: inconsistencia de etiquetas → nunca grant.
            return AccessDecision(
                False, "denied_wrong_label", None, None, "Etiqueta LBPH inconsistente", match.distance
            )
        if match.distance is not None and match.label is None:
            return AccessDecision(False, "denied_unknown", None, None, reason, match.distance)
        return AccessDecision(False, "denied_unknown", None, None, reason, match.distance)
    rows = db.query(
        "SELECT person_id FROM face_profiles WHERE model_label = ? AND enabled = 1",
        (match.label,),
    )
    if not rows:
        return AccessDecision(
            False, "denied_wrong_label", None, None, "Etiqueta sin perfil facial activo", match.distance
        )
    person_id = str(rows[0]["person_id"])
    # no doble-registrar: decide_from_recognition ya registra la decisión final
    return _evaluate_person_state(person_id, distance=match.distance)


def decide_from_recognition(match: MatchResult, *, log: bool = True) -> AccessDecision:
    """Punto de entrada para rutas web/servicio: evaluar + registrar + decidir."""
    try:
        decision = evaluate_identity(match)
    except ModelUnavailableError as exc:
        decision = AccessDecision(False, "denied_model", None, None, f"Modelo indisponible: {exc}", None)
    except Exception as exc:  # nunca otorgar en error interno
        decision = AccessDecision(False, "denied_internal_error", None, None, f"Error interno: {exc}", None)
    if log:
        _log_decision(decision)
    return decision


def _log_decision(decision: AccessDecision) -> None:
    event_service.log_access(
        person_id=decision.person_id,
        result="granted" if decision.granted else "denied",
        reason=decision.reason,
        category=decision.category,
        confidence=decision.confidence,
    )
