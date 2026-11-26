"""Vista de acceso en la pantalla TFT 3.5" SPI (ILI9486 + táctil XPT2046).

Dibuja directamente en el framebuffer de la pantalla (/dev/fbN que crea el
driver fbtft), sin escritorio, X11 ni Wayland: en la Raspberry Pi 5 es la forma
más fluida y la que menos depende de la versión del sistema.

Qué muestra:
- La cámara en vivo con caja verde (nombre) / roja (motivo) — solo informativa,
  igual que la vista de cámara del panel (no registra eventos).
- Una barra inferior con la instrucción ("Toca la pantalla para verificar").
- Al TOCAR la pantalla (o, en modo "auto", al ver un rostro estable) se hace la
  comprobación REAL de acceso: pasa por access_service.decide_from_recognition,
  que registra el evento, y se muestra una pantalla verde "Bienvenido/a" o roja
  "Acceso denegado" con el motivo durante TFT_RESULT_SECONDS.

Nunca concede rol administrativo: solo bienvenida o denegación.

Uso:
  TFT_ENABLED=true en .env  -> `python -m device.cli serve` la arranca en un hilo
  python -m device.cli tft        -> solo la pantalla (sin la API web)
  python -m device.cli tft-test   -> barras de color + coordenadas del táctil
"""
from __future__ import annotations

import os
import re
import struct
import threading
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from . import access_service, camera, config, event_service, preview_overlay
from .camera import CameraDisconnectedError
from .face_detector import FaceDetector
from .face_recognizer import ModelUnavailableError, crop_face, get_recognizer

# Colores BGR
VERDE = (60, 170, 60)
ROJO = (50, 50, 200)
GRIS = (90, 90, 90)
BLANCO = (255, 255, 255)
NEGRO = (0, 0, 0)

MOTIVOS = {
    "denied_unknown": "Rostro no reconocido",
    "denied_suspended": "Persona suspendida",
    "denied_revoked": "Permiso revocado",
    "denied_expired": "Permiso vencido",
    "denied_no_role": "Sin rol de acceso",
    "denied_wrong_label": "Perfil facial inconsistente",
    "denied_model": "Modelo sin entrenar",
    "denied_internal_error": "Error interno",
    "no_face": "No se detecto ningun rostro",
    "camera": "Camara desconectada",
}


class TFTNotFoundError(RuntimeError):
    """No se encontró el framebuffer de la pantalla TFT."""


# --------------------------------------------------------------- framebuffer

@dataclass
class FramebufferInfo:
    device: str
    width: int
    height: int
    bpp: int
    stride: int


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").strip()


def find_framebuffer(sysfs_root: str = "/sys/class/graphics",
                     dev_root: str = "/dev") -> FramebufferInfo:
    """Busca el framebuffer de la TFT. Respeta TFT_FB_DEVICE si está definido."""
    candidates = sorted(Path(sysfs_root).glob("fb[0-9]*"))
    wanted = config.TFT_FB_DEVICE.strip()
    for fb in candidates:
        name = _read(fb / "name") if (fb / "name").exists() else ""
        dev = f"{dev_root}/{fb.name}"
        if wanted:
            if os.path.basename(wanted) != fb.name:
                continue
        elif "ili9486" not in name.lower():
            continue
        w, h = (int(v) for v in _read(fb / "virtual_size").split(","))
        bpp = int(_read(fb / "bits_per_pixel"))
        stride = int(_read(fb / "stride")) if (fb / "stride").exists() else w * bpp // 8
        return FramebufferInfo(dev, w, h, bpp, stride)
    if wanted:
        raise TFTNotFoundError(f"No existe el framebuffer {wanted}")
    names = ", ".join(
        f"{fb.name}={_read(fb / 'name') if (fb / 'name').exists() else '?'}" for fb in candidates
    ) or "ninguno"
    raise TFTNotFoundError(
        "No se encontró la pantalla TFT (framebuffer ili9486). Framebuffers: "
        f"{names}. ¿Ejecutaste scripts/instalar_pantalla_tft.sh y reiniciaste?"
    )


def bgr_to_rgb565(img: np.ndarray) -> np.ndarray:
    """BGR uint8 (H, W, 3) -> RGB565 little-endian uint16 (H, W)."""
    b = img[:, :, 0].astype(np.uint16)
    g = img[:, :, 1].astype(np.uint16)
    r = img[:, :, 2].astype(np.uint16)
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


class Framebuffer:
    def __init__(self, info: FramebufferInfo):
        self.info = info
        self._f = open(info.device, "r+b", buffering=0)

    @property
    def size(self) -> tuple[int, int]:
        return self.info.width, self.info.height

    def show(self, img_bgr: np.ndarray) -> None:
        w, h = self.size
        if img_bgr.shape[1] != w or img_bgr.shape[0] != h:
            img_bgr = cv2.resize(img_bgr, (w, h))
        if self.info.bpp == 16:
            pixels = bgr_to_rgb565(img_bgr).astype("<u2")
        elif self.info.bpp == 32:
            pixels = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
        else:
            raise TFTNotFoundError(f"Profundidad de color no soportada: {self.info.bpp} bpp")
        row_bytes = w * self.info.bpp // 8
        data = pixels.tobytes()
        if self.info.stride == row_bytes:
            self._f.seek(0)
            self._f.write(data)
        else:  # filas con relleno
            for y in range(h):
                self._f.seek(y * self.info.stride)
                self._f.write(data[y * row_bytes:(y + 1) * row_bytes])

    def clear(self) -> None:
        w, h = self.size
        self.show(np.zeros((h, w, 3), dtype=np.uint8))

    def close(self) -> None:
        try:
            self._f.close()
        except OSError:
            pass


# --------------------------------------------------------------------- táctil

EV_KEY, EV_ABS = 0x01, 0x03
ABS_X, ABS_Y = 0x00, 0x01
BTN_TOUCH = 0x14A
_EVENT = struct.Struct("llHHi")  # struct input_event (timeval + type + code + value)


def find_touch_device(proc_devices: str = "/proc/bus/input/devices") -> str | None:
    if config.TFT_TOUCH_DEVICE:
        return config.TFT_TOUCH_DEVICE
    try:
        text = Path(proc_devices).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for block in text.split("\n\n"):
        if re.search(r'N: Name=".*(ADS7846|XPT2046).*"', block, re.I):
            m = re.search(r"\b(event\d+)\b", block)
            if m:
                return f"/dev/input/{m.group(1)}"
    return None


@dataclass
class TouchCalibration:
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    swap: bool

    @classmethod
    def parse(cls, text: str) -> "TouchCalibration":
        parts = [p.strip() for p in text.split(",")]
        if len(parts) != 5:
            raise ValueError("TFT_TOUCH_CAL debe ser 'xmin,xmax,ymin,ymax,swap'")
        return cls(float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]),
                   parts[4] in ("1", "true", "si", "yes"))

    def to_screen(self, raw_x: int, raw_y: int, width: int, height: int) -> tuple[int, int]:
        """Igual que evdev de X11: primero SwapAxes, luego Calibration."""
        x, y = (raw_y, raw_x) if self.swap else (raw_x, raw_y)
        sx = (x - self.xmin) / ((self.xmax - self.xmin) or 1) * width
        sy = (y - self.ymin) / ((self.ymax - self.ymin) or 1) * height
        return (int(min(max(sx, 0), width - 1)), int(min(max(sy, 0), height - 1)))


class TouchReader:
    """Lee el dispositivo de entrada en un hilo y guarda el último toque."""

    def __init__(self, device: str):
        self.device = device
        self._taps: list[tuple[int, int]] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="tft-touch", daemon=True)

    def start(self) -> "TouchReader":
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()

    def pop_tap(self) -> tuple[int, int] | None:
        """Devuelve el último toque (x, y crudos) y vacía la cola."""
        with self._lock:
            tap = self._taps[-1] if self._taps else None
            self._taps.clear()
        return tap

    def feed(self, data: bytes, state: dict) -> None:
        """Procesa bytes de eventos (separado para poder probarlo)."""
        for off in range(0, len(data) - _EVENT.size + 1, _EVENT.size):
            _s, _us, etype, code, value = _EVENT.unpack_from(data, off)
            if etype == EV_ABS and code == ABS_X:
                state["x"] = value
            elif etype == EV_ABS and code == ABS_Y:
                state["y"] = value
            elif etype == EV_KEY and code == BTN_TOUCH:
                if value == 1:
                    state["down"] = True
                elif value == 0 and state.get("down"):
                    state["down"] = False
                    # se registra al LEVANTAR el dedo, con la última posición
                    with self._lock:
                        self._taps.append((state.get("x", 0), state.get("y", 0)))

    def _loop(self) -> None:
        state: dict = {}
        while not self._stop.is_set():
            try:
                with open(self.device, "rb", buffering=0) as f:
                    while not self._stop.is_set():
                        data = f.read(_EVENT.size * 16)
                        if not data:
                            break
                        self.feed(data, state)
            except OSError:
                time.sleep(2)  # táctil ausente o sin permisos: reintentar


# ------------------------------------------------------------------- dibujo

def _ascii(text: str) -> str:
    """Las fuentes de OpenCV no tienen tildes ni ñ: se quitan para mostrar."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def _fit_cover(frame: np.ndarray, width: int, height: int) -> np.ndarray:
    """Escala para cubrir toda la pantalla y recorta el sobrante centrado."""
    fh, fw = frame.shape[:2]
    scale = max(width / fw, height / fh)
    resized = cv2.resize(frame, (max(width, round(fw * scale)), max(height, round(fh * scale))),
                         interpolation=cv2.INTER_AREA)
    rh, rw = resized.shape[:2]
    x0, y0 = (rw - width) // 2, (rh - height) // 2
    return resized[y0:y0 + height, x0:x0 + width]


def _text_center(img: np.ndarray, text: str, cy: int, scale: float, color, thickness: int) -> None:
    text = _ascii(text)
    font = cv2.FONT_HERSHEY_SIMPLEX
    # reducir hasta que quepa en el ancho
    while scale > 0.4:
        (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
        if tw <= img.shape[1] - 16:
            break
        scale -= 0.1
    (tw, th), _ = cv2.getTextSize(text, font, scale, thickness)
    x = max(8, (img.shape[1] - tw) // 2)
    cv2.putText(img, text, (x, cy + th // 2), font, scale, color, thickness, cv2.LINE_AA)


def render_live(frame: np.ndarray, width: int, height: int, hint: str) -> np.ndarray:
    out = _fit_cover(frame, width, height)
    bar_h = max(30, height // 9)
    overlay = out.copy()
    cv2.rectangle(overlay, (0, height - bar_h), (width, height), NEGRO, -1)
    out = cv2.addWeighted(overlay, 0.6, out, 0.4, 0)
    _text_center(out, hint, height - bar_h // 2, 0.6, BLANCO, 1)
    return out


def render_message(width: int, height: int, color, title: str, subtitle: str = "") -> np.ndarray:
    img = np.full((height, width, 3), color, dtype=np.uint8)
    if subtitle:
        _text_center(img, title, int(height * 0.40), 1.3, BLANCO, 3)
        _text_center(img, subtitle, int(height * 0.66), 0.8, BLANCO, 2)
    else:
        _text_center(img, title, height // 2, 1.2, BLANCO, 3)
    return img


def render_decision(width: int, height: int, granted: bool, category: str,
                    display_name: str | None) -> np.ndarray:
    if granted:
        return render_message(width, height, VERDE, "Bienvenido/a", display_name or "")
    return render_message(width, height, ROJO, "Acceso denegado",
                          MOTIVOS.get(category, "Acceso denegado"))


# ----------------------------------------------------------- comprobación real

@dataclass
class CheckResult:
    granted: bool
    category: str
    display_name: str | None


def run_access_check(detector: FaceDetector) -> CheckResult:
    """Misma lógica que POST /api/access/check: reconoce, decide y REGISTRA."""
    try:
        frame = camera.get_source().read()
    except CameraDisconnectedError:
        return CheckResult(False, "camera", None)
    faces = sorted(detector.detect(frame), key=lambda r: r[2] * r[3], reverse=True)
    if not faces:
        return CheckResult(False, "no_face", None)
    try:
        match = get_recognizer().predict(crop_face(frame, faces[0]))
    except ModelUnavailableError as exc:
        event_service.log_access(person_id=None, result="denied", reason=str(exc),
                                 category="denied_model")
        return CheckResult(False, "denied_model", None)
    decision = access_service.decide_from_recognition(match)
    return CheckResult(decision.granted, decision.category, decision.display_name)


# -------------------------------------------------------------------- bucle

class TFTDisplay:
    def __init__(self, fb: Framebuffer, touch: TouchReader | None = None,
                 detector: FaceDetector | None = None):
        self.fb = fb
        self.touch = touch
        self.detector = detector or FaceDetector()
        self.mode = config.TFT_MODE if config.TFT_MODE in ("toque", "auto") else "toque"
        self._stop = threading.Event()
        self._result_until = 0.0
        self._face_streak = 0
        self._cooldown_until = 0.0

    @property
    def hint(self) -> str:
        if self.mode == "auto":
            return "Mira a la camara para verificar"
        if self.touch is None:
            return "Pantalla tactil no detectada"
        return "Toca la pantalla para verificar"

    def stop(self) -> None:
        self._stop.set()

    def _show_result(self, res: CheckResult) -> None:
        w, h = self.fb.size
        self.fb.show(render_decision(w, h, res.granted, res.category, res.display_name))
        self._result_until = time.time() + config.TFT_RESULT_SECONDS
        self._cooldown_until = self._result_until + 2.0

    def step(self) -> None:
        """Un ciclo: lee toque, decide qué dibujar y lo dibuja."""
        w, h = self.fb.size
        now = time.time()
        tap = self.touch.pop_tap() if self.touch else None
        if now < self._result_until:
            return  # se mantiene la pantalla de resultado
        if tap is not None and self.mode == "toque":
            self.fb.show(render_message(w, h, GRIS, "Verificando..."))
            self._show_result(run_access_check(self.detector))
            return
        try:
            frame = camera.get_source().read()
        except CameraDisconnectedError:
            self.fb.show(render_message(w, h, GRIS, "Camara desconectada"))
            return
        faces = self.detector.detect(frame)
        if config.TFT_LIVE_RECOGNITION:
            frame, _ = preview_overlay.annotate_frame(frame, faces, get_recognizer())
        self.fb.show(render_live(frame, w, h, self.hint))
        if self.mode == "auto":
            self._face_streak = self._face_streak + 1 if faces else 0
            if self._face_streak >= max(3, int(config.TFT_FPS)) and now >= self._cooldown_until:
                self._face_streak = 0
                self._show_result(run_access_check(self.detector))

    def run(self) -> None:
        period = 1.0 / max(1.0, config.TFT_FPS)
        _disable_console_cursor()
        try:
            while not self._stop.is_set():
                t0 = time.time()
                try:
                    self.step()
                except Exception as exc:  # la pantalla nunca debe tumbar el servicio
                    w, h = self.fb.size
                    try:
                        self.fb.show(render_message(w, h, GRIS, "Error", type(exc).__name__))
                    except Exception:
                        pass
                    time.sleep(1)
                time.sleep(max(0.0, period - (time.time() - t0)))
        finally:
            try:
                self.fb.clear()
            except Exception:
                pass


def _disable_console_cursor() -> None:
    """Evita que el cursor parpadeante de la consola se dibuje sobre la vista."""
    for path in ("/sys/class/graphics/fbcon/cursor_blink",):
        try:
            Path(path).write_text("0")
        except OSError:
            pass


def build_display() -> TFTDisplay:
    fb = Framebuffer(find_framebuffer())
    touch_dev = find_touch_device()
    touch = TouchReader(touch_dev).start() if touch_dev else None
    return TFTDisplay(fb, touch)


def start_in_thread() -> threading.Thread | None:
    """Arranca la pantalla dentro del proceso del servicio (comparte la cámara)."""
    try:
        display = build_display()
    except (TFTNotFoundError, OSError, RuntimeError) as exc:
        print(f"[tft] Pantalla TFT no disponible: {exc}")
        return None
    t = threading.Thread(target=display.run, name="tft-display", daemon=True)
    t.start()
    print(f"[tft] Vista de acceso en {display.fb.info.device} "
          f"({display.fb.info.width}x{display.fb.info.height}), modo={display.mode}, "
          f"tactil={display.touch.device if display.touch else 'no'}")
    return t


def patron_prueba(seconds: float = 60.0) -> None:
    """Barras de color + coordenadas de cada toque (para comprobar y calibrar)."""
    info = find_framebuffer()
    fb = Framebuffer(info)
    w, h = fb.size
    print(f"[tft] Framebuffer {info.device}: {w}x{h} {info.bpp}bpp")
    touch_dev = find_touch_device()
    print(f"[tft] Táctil: {touch_dev or 'NO detectado'}")
    touch = TouchReader(touch_dev).start() if touch_dev else None
    cal = TouchCalibration.parse(config.TFT_TOUCH_CAL)
    colors = [BLANCO, (0, 255, 255), (255, 255, 0), (0, 255, 0), (255, 0, 255), (0, 0, 255),
              (255, 0, 0), NEGRO]
    base = np.zeros((h, w, 3), dtype=np.uint8)
    for i, c in enumerate(colors):
        base[:, i * w // len(colors):(i + 1) * w // len(colors)] = c
    _text_center(base, "proyectoC3 - toca la pantalla", h // 2, 0.7, (128, 128, 128), 2)
    img = base.copy()
    fb.show(img)
    end = time.time() + seconds
    try:
        while time.time() < end:
            tap = touch.pop_tap() if touch else None
            if tap:
                sx, sy = cal.to_screen(tap[0], tap[1], w, h)
                print(f"[tft] toque crudo=({tap[0]},{tap[1]}) -> pantalla=({sx},{sy})")
                img = base.copy()
                cv2.circle(img, (sx, sy), 12, (0, 0, 0), 3)
                cv2.circle(img, (sx, sy), 4, (0, 0, 255), -1)
                fb.show(img)
            time.sleep(0.05)
    finally:
        if touch:
            touch.stop()
        fb.clear()
        fb.close()
