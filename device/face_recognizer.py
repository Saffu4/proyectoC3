"""Envoltura del modelo LBPH (cv2.face) + gestión del mapa de etiquetas.

ESQUEMA DE ETIQUETAS (documentado explícitamente):
- La fuente de verdad del mapa etiqueta->persona es la tabla `face_profiles`
  (model_label INTEGER UNIQUE, person_id), no la carpeta de imágenes.
- Al crear un perfil facial se asigna label = max(model_label)+1 de la tabla.
  Esto evita reasignar etiquetas cuando se agregan personas nuevas y evita
  reindexar labels al reentrenar (LBPH se entrena solo con imágenes de
  personas con face_profiles habilitado)."""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from . import db, config


@dataclass
class MatchResult:
    label: int | None
    distance: float | None  # distancia LBPH (menor = más cercano). NOT a probability.
    accepted: bool


class ModelUnavailableError(Exception):
    """El modelo no está entrenado o el archivo está corrupto/ausente."""


def _normalize_gray(face_bgr: "np.ndarray | np.ndarray") -> np.ndarray:
    """BGR o gris -> gris normalizado a CAPTURE_SIZE x CAPTURE_SIZE."""
    if face_bgr.ndim == 3:
        face_bgr = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(face_bgr, (config.CAPTURE_SIZE, config.CAPTURE_SIZE))
    return cv2.equalizeHist(gray)


def load_face_to_train(face_bgr: np.ndarray) -> np.ndarray:
    return _normalize_gray(face_bgr)


class LBPHRecognizer:
    """Un único modelo persistente, entrenado por 'train()' desde rostros/."""
    def __init__(self):
        self._model = cv2.face.LBPHFaceRecognizer_create()
        self._trained_labels: set[int] = set()

    @property
    def model_path(self):
        return config.models_dir() / "modelo_lbph.yml"

    def is_trained(self) -> bool:
        return self.model_path.exists()

    def load(self) -> None:
        if not self.model_path.exists():
            raise ModelUnavailableError(f"No existe {self.model_path}")
        try:
            self._model.read(str(self.model_path))
        except Exception as exc:  # archivo corrupto o versión incompatible
            raise ModelUnavailableError(f"Modelo corrupto: {exc}") from exc

    def train(self) -> int:
        """Entrena con las imágenes de rostros/<person_id>/ de perfiles habilitados.

        Devuelve la cantidad de imágenes usadas."""
        profile_rows = db.query(
            "SELECT model_label, person_id FROM face_profiles WHERE enabled = 1"
        )
        images: list[np.ndarray] = []
        labels: list[int] = []
        used = 0
        for row in profile_rows:
            folder = config.faces_dir(row["person_id"])
            if not folder.exists():
                continue
            for img_path in sorted(folder.glob("*.jpg")):
                img = cv2.imread(str(img_path))
                if img is None:
                    continue
                images.append(_normalize_gray(img))
                labels.append(int(row["model_label"]))
                used += 1
        if not images:
            # Nadie tiene imágenes válidas: borrar el modelo para que no quede
            # un modelo desincronizado con la base de datos.
            if self.model_path.exists():
                self.model_path.unlink()
            self._trained_labels.clear()
            raise ModelUnavailableError(
                "No hay imágenes de rostro para entrenar: el modelo queda vacío"
            )
        self._model.train(images, np.array(labels, dtype=np.int32))
        config.models_dir().mkdir(parents=True, exist_ok=True)
        self._model.write(str(self.model_path))
        self._trained_labels = set(labels)
        return used

    def predict(self, face_bgr: np.ndarray) -> MatchResult:
        """Predice la proximidad del rostro al modelo. Devuelve MatchResult."""
        if not self.model_path.exists():
            raise ModelUnavailableError("Modelo LBPH no entrenado")
        if not self._trained_labels:
            try:
                self.load()
            except Exception as exc:
                raise ModelUnavailableError(f"Fallo al cargar modelo: {exc}") from exc
            rows = db.query("SELECT model_label FROM face_profiles WHERE enabled=1")
            self._trained_labels = {int(r["model_label"]) for r in rows}
        gray = _normalize_gray(face_bgr)
        try:
            label, distance = self._model.predict(gray)
        except cv2.error as exc:
            raise ModelUnavailableError(f"Error de predicción lbph: {exc}") from exc
        if label is None:
            label = -1
        match = label >= 0 and label in self._trained_labels
        accepted = match and float(distance) <= config.LBPH_THRESHOLD
        return MatchResult(
            label=int(label) if match else None,
            distance=float(distance) if distance is not None else None,
            accepted=bool(accepted),
        )


_shared: "LBPHRecognizer | None" = None


def get_recognizer() -> "LBPHRecognizer":
    global _shared
    if _shared is None:
        _shared = LBPHRecognizer()
    return _shared


def invalidate_shared() -> None:
    """Después de reentrenar o cambiar perfiles, fuerza recarga del modelo."""
    global _shared
    _shared = None


LABEL_COUNTER_KEY = "model_label_counter"


def next_model_label() -> int:
    """Asigna labels de forma estable y SIN REUTILIZAR, empezando en 1.

    Antes se usaba max(model_label)+1 de face_profiles: al borrar a la persona
    con la etiqueta más alta, la siguiente persona heredaba su número y, hasta
    reentrenar, el rostro de la persona borrada se reconocía como la nueva.
    Ahora un contador persistente en `settings` solo crece (se toma el mayor
    entre el contador y el máximo de la tabla, por compatibilidad con bases
    existentes). La lectura y escritura van en la misma conexión/bloqueo."""
    with db.get_conn() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (LABEL_COUNTER_KEY,)
        ).fetchone()
        try:
            counter = int(row["value"]) if row else 0
        except (TypeError, ValueError):
            counter = 0
        max_db = conn.execute(
            "SELECT COALESCE(MAX(model_label), 0) AS m FROM face_profiles"
        ).fetchone()["m"]
        label = max(counter, int(max_db)) + 1
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (LABEL_COUNTER_KEY, str(label)),
        )
    return label


def crop_face(frame: np.ndarray, rect) -> np.ndarray:
    """Recorte del rostro con el margen de captura (FACE_MARGIN, 15 % por defecto).

    Se usa IGUAL al capturar (entrenamiento) y al reconocer, para que el modelo
    compare imágenes encuadradas de la misma forma."""
    (x, y, w, h) = rect
    margen_x = int(w * config.FACE_MARGIN)
    margen_y = int(h * config.FACE_MARGIN)
    H, W = frame.shape[:2]
    x1, y1 = max(0, x - margen_x), max(0, y - margen_y)
    x2, y2 = min(W, x + w + margen_x), min(H, y + h + margen_y)
    return frame[y1:y2, x1:x2]
