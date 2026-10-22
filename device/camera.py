"""Abstracción de cámara. La captura corre en un hilo único; ninguna ruta HTTP
abre la cámara por sí misma (evita 'device busy' con la Pi 5)."""
from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

import cv2
import numpy as np

from . import config


class CameraDisconnectedError(Exception):
    pass


class FrameSource:
    def read(self) -> np.ndarray:  # pragma: no cover - interfaz
        raise NotImplementedError

    def stop(self) -> None:  # pragma: no cover - interfaz
        raise NotImplementedError


class WebCam(FrameSource):
    """Captura en hilo en bucle: siempre hay el frame más reciente disponible.
    Si la cámara falla, el hilo intenta reabrirla cada REOPEN_SECONDS."""

    REOPEN_SECONDS = 3.0

    def __init__(self, index: int | None = None):
        self._index = index if index is not None else config.CAMERA_INDEX
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._last_ok = 0.0
        self._stopped = False
        self._thread = threading.Thread(target=self._loop, name="camera", daemon=True)
        self._thread.start()

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        # CAP_V4L2 en Raspberry Pi (Debian); en Windows OpenCV elige el backend.
        backend = cv2.CAP_V4L2 if os.name == "posix" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self._index, backend)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAPTURE_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAPTURE_HEIGHT)
        if not cap.isOpened():
            return None
        ok, frame = cap.read()
        if not ok:
            cap.release()
            return None
        return cap

    def _loop(self) -> None:
        while not self._stopped:
            cap = self._open_capture()
            if cap is None:
                time.sleep(self.REOPEN_SECONDS)
                continue
            while not self._stopped:
                ok, frame = cap.read()
                with self._lock:
                    if ok:
                        self._frame = frame
                    else:
                        self._frame = None
                    self._last_ok = time.time() if ok else self._last_ok
                if not ok:
                    break
                time.sleep(0.02)
            cap.release()
            time.sleep(self.REOPEN_SECONDS)

    def read(self) -> np.ndarray:
        with self._lock:
            frame = self._frame
            stale = (time.time() - self._last_ok) > 3.0
        if frame is None or self._stopped:
            raise CameraDisconnectedError("Cámara no disponible (sin frames)")
        if stale:
            raise CameraDisconnectedError("Cámara congelada (sin frames frescos)")
        return frame

    def stop(self) -> None:
        self._stopped = True


class StaticSource(FrameSource):
    """Fuente sintética para pruebas: devuelve la siguiente imagen de la lista."""

    def __init__(self, images: list[np.ndarray]):
        if not images:
            raise ValueError("StaticSource necesita al menos una imagen")
        self._images = images
        self._i = 0

    def read(self) -> np.ndarray:
        img = self._images[min(self._i, len(self._images) - 1)]
        self._i += 1
        return img

    def stop(self) -> None:
        pass


class NoCameraSource(FrameSource):
    """Simula cámara desconectada (pruebas)."""

    def read(self) -> np.ndarray:
        raise CameraDisconnectedError("Cámara simulada como desconectada")

    def stop(self) -> None:
        pass


_source: Optional[FrameSource] = None
_source_lock = threading.Lock()


def set_source(source: FrameSource) -> None:
    """Inyecta una fuente (app.py usa WebCam; los tests usan Static/NoCamera)."""
    global _source
    with _source_lock:
        if _source is not None:
            _source.stop()
        _source = source


def get_source() -> FrameSource:
    global _source
    with _source_lock:
        if _source is None:
            mode = os.environ.get("CAM_SOURCE", "webcam")
            if mode == "none":
                _source = NoCameraSource()
            else:
                _source = WebCam()
        return _source
