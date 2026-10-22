"""Detección de rostros con Haar Cascade (la misma familia de detector que
típicamente usa detector.py en el proyecto original). Persistente y sin abrir
nuevos VideoCapture."""
from __future__ import annotations

import cv2
import os
import numpy as np

from . import config


class FaceDetector:
    def __init__(self, scale_factor: float = 1.15, min_neighbors: int = 5):
        candidates = list(config.CASCADE_CANDIDATES)
        # ruta del paquete pip (cv2.data) como último recurso
        try:
            candidates.append(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        except AttributeError:
            pass
        self._cascade = None
        for path in candidates:
            cascade = cv2.CascadeClassifier(path)
            if not cascade.empty():
                self._cascade = cascade
                break
        if self._cascade is None:
            raise RuntimeError(
                "No se pudo cargar el Haar Cascade. Rutas probadas: "
                + "; ".join(candidates)
                + ". Ajusta CASCADE_PATH si la instalación de OpenCV es distinta."
            )
        self._scale_factor = scale_factor
        self._min_neighbors = min_neighbors

    def detect(self, frame_bgr: np.ndarray) -> list[tuple[int, int, int, int]]:
        """Devuelve rects (x, y, w, h) en el frame original."""
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        rects = self._cascade.detectMultiScale(
            gray, scaleFactor=self._scale_factor, minNeighbors=self._min_neighbors,
            flags=cv2.CASCADE_SCALE_IMAGE, minSize=(80, 80),
        )
        return [(int(x), int(y), int(w), int(h)) for (x, y, w, h) in rects]

    def has_face(self, frame_bgr: np.ndarray) -> bool:
        return len(self.detect(frame_bgr)) > 0
