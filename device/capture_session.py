"""Sesión de captura con retroalimentación en vivo.

Una sola sesión activa a la vez (proceso global). La UI del panel ve:
  - preview MJPEG con caja verde/roja y contador dibujado,
  - estado vía polling: guardados, guía en texto, nitidez/luz/distancia.

Reutiliza el pipeline base (cara más grande, margen 15%, 200×200, equalizeHist,
ritmo ~0.4 s) y añade control de calidad ANTES de guardar (no se guardan
tomas borrosas, oscuras o con el rostro a media distancia)."""
from __future__ import annotations

import threading
import time
import uuid
import cv2
import numpy as np

from . import camera, config, db
from .face_detector import FaceDetector
from .face_recognizer import load_face_to_train

# Umbrales de calidad (calibles por env)
BLUR_MIN = 60.0        # variancia del Laplaciano: menor = borroso
BRIGHT_MIN = 45.0      # luminancia media mínima (0-255)
FACE_MIN_W = 110       # px mínimos de ancho del rostro (acércate si menos)


class CaptureBusyError(Exception):
    """Ya hay una sesión de captura en curso."""


class SessionNotFoundError(Exception):
    pass


def _recent_guidance(*, face: bool, sharp: bool, bright_ok: bool, close_ok: bool) -> str:
    if not face:
        return "Ningún rostro visible: mira a la cámara"
    if not bright_ok:
        return "Poca luz: busca iluminación frontal"
    if not close_ok:
        return "Acércate un poco a la cámara"
    if not sharp:
        return "Rostro borroso: mantente quieto"
    return "Posición correcta: mantente así"


class CaptureSession:
    def __init__(self, person_id: str, target: int):
        self.id = str(uuid.uuid4())
        self.person_id = person_id
        self.target = max(1, min(int(target), 60))
        self.saved = 0
        self.status = "running"  # running | done | cancelled | error
        self.guidance = "Iniciando cámara…"
        self.error: str | None = None
        self.created_at = time.time()
        self._preview: np.ndarray | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._loop, name=f"capture-{self.id[:6]}", daemon=True)

    # ------------------------------------------------------------------ state

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "session_id": self.id,
                "person_id": self.person_id,
                "target": self.target,
                "saved": self.saved,
                "status": self.status,
                "guidance": self.guidance,
                "error": self.error,
                "has_preview": self._preview is not None,
            }

    def request_stop(self, *, cancelled: bool = True) -> None:
        self._stop.set()

    def _finish(self, status: str, error: str | None = None) -> None:
        with self._lock:
            if self.status == "running":
                self.status = status
                self.error = error
                if status == "done":
                    self.guidance = f"Completado: {self.saved}/{self.target} rostros"
        if status == "done":
            db.execute(
                "INSERT INTO audit_log (action, actor, detail, timestamp) VALUES (?, ?, ?, ?)",
                ("faces_capture_done", "panel", f"person={self.person_id} saved={self.saved}/{self.target}", db.utcnow_iso()),
            )

    # ------------------------------------------------------------------ preview

    def read_preview(self) -> np.ndarray | None:
        with self._lock:
            frame = self._preview
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 72])
        return buf.tobytes() if ok else None  # type: ignore[return-value]

    def _annotate(self, frame: np.ndarray, rect, sharp: bool) -> np.ndarray:
        out = frame.copy()
        if rect:
            (x, y, w, h) = rect
            color = (0, 200, 0) if sharp else (0, 120, 255)  # verde / naranja
            cv2.rectangle(out, (x, y), (x + w, y + h), color, 2)
        texto = f"{self.saved}/{self.target}"
        cv2.putText(out, texto, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
        cv2.putText(out, texto, (12, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 160, 0), 1)
        return out

    # ------------------------------------------------------------------ loop

    def _loop(self) -> None:
        try:
            detector = FaceDetector()
        except RuntimeError as exc:
            self._finish("error", f"Detector no disponible: {exc}")
            return

        deadline = self.created_at + 180.0  # timeout duro de sesión
        while not self._stop.is_set() and time.time() < deadline:
            try:
                frame = camera.get_source().read()
            except camera.CameraDisconnectedError as exc:
                self._finish("error", f"Cámara: {exc}")
                return

            faces = detector.detect(frame)
            faces = sorted(faces, key=lambda c: c[2] * c[3], reverse=True)
            rect = faces[0] if faces else None

            can_save = False
            gray_mean = 0.0
            blur_score = 0.0
            if rect:
                (x, y, w, h) = rect
                roi_gray = cv2.cvtColor(frame[y : y + h, x : x + w], cv2.COLOR_BGR2GRAY)
                gray_mean = float(roi_gray.mean())
                blur_score = float(cv2.Laplacian(roi_gray, cv2.CV_64F).var())
                can_save = (
                    w >= FACE_MIN_W
                    and gray_mean >= BRIGHT_MIN
                    and blur_score >= BLUR_MIN
                )
            self.guidance = _recent_guidance(
                face=rect is not None,
                sharp=blur_score >= BLUR_MIN,
                bright_ok=gray_mean >= BRIGHT_MIN,
                close_ok=rect is None or rect[2] >= FACE_MIN_W,
            )

            # guardar tomas válidas al ritmo del base (~0.4 s entre guardados)
            if can_save:
                (x, y, w, h) = rect
                margen_x = int(w * config.FACE_MARGIN)
                margen_y = int(h * config.FACE_MARGIN)
                H, W = frame.shape[:2]
                x1, y1 = max(0, x - margen_x), max(0, y - margen_y)
                x2, y2 = min(W, x + w + margen_x), min(H, y + h + margen_y)
                face_img = load_face_to_train(frame[y1:y2, x1:x2])
                folder = config.faces_dir(self.person_id)
                config.ensure_data_dirs()
                folder.mkdir(parents=True, exist_ok=True)
                folder.chmod(0o700)
                filename = folder / f"{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}_{int(time.monotonic() * 1000) % 10000}_{self.saved}.jpg"
                cv2.imwrite(str(filename), face_img)
                with self._lock:
                    self.saved += 1
                    if self.saved >= self.target:
                        self._want_done = True

            annotated = self._annotate(frame, rect, sharp=blur_score >= BLUR_MIN)
            finish_now = False
            with self._lock:
                self._preview = annotated
                finish_now = getattr(self, "_want_done", False)
            if finish_now:
                self._finish("done")
                return

            time.sleep(max(0.05, config.CAPTURE_PACE_SECONDS))

        if self.saved >= self.target:
            self._finish("done")
        elif self._stop.is_set():
            self._finish("cancelled")
        else:
            self._finish("cancelled", f"Tiempo agotado con {self.saved}/{self.target} capturados")


_registry: dict[str, CaptureSession] = {}
_reg_lock = threading.Lock()


def start_session(person_id: str, target: int) -> CaptureSession:
    with _reg_lock:
        # purga sesiones terminadas
        for sid, ses in list(_registry.items()):
            if ses.status != "running":
                _registry.pop(sid, None)
        for ses in _registry.values():
            if ses.status == "running":
                raise CaptureBusyError("Ya hay una sesión de captura en curso: deténgela primero")
        ses = CaptureSession(person_id, target)
        _registry[ses.id] = ses
    ses._thread.start()
    return ses


def get_session(sid: str) -> CaptureSession:
    ses = _registry.get(sid)
    if ses is None:
        raise SessionNotFoundError("Sesión de captura no encontrada o expirada")
    return ses
