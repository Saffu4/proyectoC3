"""Superposición de reconocimiento en la vista previa de la cámara.

Reglas:
- Es SOLO informativa: usa evaluate_identity() (sin log de eventos) para no
  spamear access_events ni audit_log con cada fotograma. La única ruta que
  registra accesos sigue siendo /api/access/check.
- Jamás otorga permisos: la decisión real de una comprobación pasa por
  access_service.decide_from_recognition (con registro), no por esta vista.
- Modelo no entrenado → indicador explícito, nunca "acceso".
"""
from __future__ import annotations

import cv2
import numpy as np

from . import access_service
from .face_recognizer import LBPHRecognizer, MatchResult, ModelUnavailableError

_COLOR_OK = (80, 220, 100)      # verde
_COLOR_DENY = (80, 80, 230)     # rojo
_COLOR_MODEL = (160, 160, 160)  # gris

_SHORT_REASON = {
    "denied_unknown": "Desconocido",
    "denied_suspended": "Suspendido",
    "denied_revoked": "Revocado",
    "denied_expired": "Vencido",
    "denied_no_role": "Sin rol de acceso",
    "denied_wrong_label": "Etiqueta inconsistente",
    "denied_model": "Modelo no entrenado",
}


def _label_for(category: str, display_name: str | None) -> str:
    if category == "welcome":
        return display_name or "Reconocido"
    if category == "denied_model":
        return _SHORT_REASON["denied_model"]
    return _SHORT_REASON.get(category, "Denegado")


def annotate_frame(
    frame: np.ndarray,
    faces: list[tuple[int, int, int, int]],
    recognizer: LBPHRecognizer,
) -> tuple[np.ndarray, list[dict]]:
    """Devuelve (fotograma anotado, resultados por rostro).

    Cada rostro: caja verde + nombre si acceso; roja + motivo si no;
    gris 'Modelo no entrenado' si no hay modelo.
    """
    annotated = frame.copy()
    results: list[dict] = []
    model_ok = recognizer.is_trained()
    for (x, y, w, h) in faces:
        H, W = annotated.shape[:2]
        x2, y2 = min(W, x + w), min(H, y + h)
        category = "denied_model"
        display_name = None
        distance = None
        color = _COLOR_MODEL
        if model_ok and w > 0 and h > 0:
            try:
                match: MatchResult = recognizer.predict(annotated[y:y2, x:x2])
                distance = match.distance
                try:
                    decision = access_service.evaluate_identity(match)
                except Exception:
                    decision = access_service.AccessDecision(
                        False, "denied_internal_error", None, None, "Error interno", match.distance
                    )
                category = decision.category
                display_name = decision.display_name
                color = _COLOR_OK if decision.granted else _COLOR_DENY
            except ModelUnavailableError:
                category = "denied_model"
        cv2.rectangle(annotated, (x, y), (x2, y2), color, 2)
        text = _label_for(category, display_name)
        if distance is not None:
            text = f"{text}  ({distance:.0f})"
        _draw_label(annotated, x, y, text, color)
        results.append(
            {"category": category, "display_name": display_name, "distance": distance}
        )
    return annotated, results


def _draw_label(img: np.ndarray, x: int, y: int, text: str, color) -> None:
    (tw, th), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    ty = max(th + 6, y - 8)
    ty2 = min(img.shape[0], ty + baseline + 6)
    cv2.rectangle(img, (x, ty - th - 6), (x + tw + 10, ty2), color, -1)
    cv2.putText(
        img, text, (x + 5, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 20, 20), 1, cv2.LINE_AA
    )
