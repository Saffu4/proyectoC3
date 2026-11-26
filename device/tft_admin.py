"""Menú de administración táctil en la pantalla TFT 3.5".

Se abre con el botón "Admin" de la vista de acceso y pide un PIN numérico
(se configura con `python -m device.cli tft-pin`). Reconocer un rostro NUNCA
abre este menú: solo el PIN.

Permite, sin teclado ni panel web:
- Nueva persona: escribir el nombre con un teclado en pantalla, tomar las fotos
  (vista en vivo con contador y guía de luz/distancia) y entrenar el modelo.
- Personas: ver la lista; por persona, tomar más fotos, suspender/activar o eliminar.
- Entrenar modelo.

Todo pasa por people_service / capture_session (lo mismo que el panel web) y
queda en audit_log con actor "pantalla". Sale solo tras 90 s sin tocar.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import cv2
import numpy as np

from . import capture_session, people_service

# Colores BGR
FONDO = (40, 32, 28)
AZUL = (170, 110, 30)
VERDE = (60, 150, 60)
ROJO = (50, 50, 190)
GRIS = (95, 95, 95)
BLANCO = (255, 255, 255)
NEGRO = (0, 0, 0)

INACTIVITY_SECONDS = 90
PIN_MAX_FAILS = 5
PIN_LOCK_SECONDS = 60
CAPTURE_TARGET = 20
MIN_PHOTOS_TO_TRAIN = 5

ESTADOS = {"active": "Activo", "suspended": "Suspendido", "revoked": "Revocado"}


def _ascii(text: str) -> str:
    from .tft_display import _ascii as a

    return a(text)


def _put(img, text, x, y, scale=0.6, color=BLANCO, thick=1, max_w=None):
    text = _ascii(text)
    font = cv2.FONT_HERSHEY_SIMPLEX
    if max_w:
        while scale > 0.35 and cv2.getTextSize(text, font, scale, thick)[0][0] > max_w:
            scale -= 0.05
    cv2.putText(img, text, (int(x), int(y)), font, scale, color, thick, cv2.LINE_AA)


def _put_center(img, text, cx, cy, scale=0.6, color=BLANCO, thick=1, max_w=None):
    text = _ascii(text)
    font = cv2.FONT_HERSHEY_SIMPLEX
    if max_w:
        while scale > 0.35 and cv2.getTextSize(text, font, scale, thick)[0][0] > max_w:
            scale -= 0.05
    (tw, th), _ = cv2.getTextSize(text, font, scale, thick)
    cv2.putText(img, text, (int(cx - tw / 2), int(cy + th / 2)), font, scale, color, thick, cv2.LINE_AA)


@dataclass
class Button:
    x: int
    y: int
    w: int
    h: int
    label: str
    action: Callable[[], "Screen | None | str"]
    color: tuple = AZUL
    scale: float = 0.6

    def hit(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    def draw(self, img) -> None:
        cv2.rectangle(img, (self.x + 2, self.y + 2), (self.x + self.w - 3, self.y + self.h - 3),
                      self.color, -1)
        _put_center(img, self.label, self.x + self.w / 2, self.y + self.h / 2, self.scale,
                    BLANCO, 1 if self.scale < 0.7 else 2, max_w=self.w - 10)


KEEP = "keep"   # acción que no cambia de pantalla (solo redibuja)
EXIT = "exit"   # salir del menú


class Screen:
    title = ""
    dynamic = False  # True = redibujar en cada ciclo (vista de cámara)

    def __init__(self, ui: "AdminUI"):
        self.ui = ui
        self.buttons: list[Button] = []

    @property
    def size(self) -> tuple[int, int]:
        return self.ui.width, self.ui.height

    def layout(self) -> None:
        """Crea self.buttons según el tamaño de pantalla."""

    def tick(self) -> "Screen | None | str":
        return KEEP

    def busy(self) -> bool:
        """True mientras una operación larga impide salir por inactividad."""
        return False

    def tap(self, x: int, y: int) -> "Screen | None | str":
        for b in self.buttons:
            if b.hit(x, y):
                return b.action()
        return KEEP

    def render(self) -> np.ndarray:
        w, h = self.size
        img = np.full((h, w, 3), FONDO, dtype=np.uint8)
        if self.title:
            cv2.rectangle(img, (0, 0), (w, 40), (70, 55, 45), -1)
            _put(img, self.title, 10, 27, 0.65, BLANCO, 2, max_w=w - 20)
        self.draw_body(img)
        for b in self.buttons:
            b.draw(img)
        return img

    def draw_body(self, img) -> None:
        pass


# ------------------------------------------------------------------ pantallas

class MessageScreen(Screen):
    def __init__(self, ui, title, lines=(), color=GRIS, next_screen: Callable | None = None):
        super().__init__(ui)
        self.msg_title, self.lines, self.color = title, list(lines), color
        self.next_screen = next_screen or (lambda: MenuScreen(ui))
        w, h = self.size
        self.buttons = [Button(w // 2 - 80, h - 70, 160, 56, "OK", self.next_screen, AZUL, 0.8)]

    def render(self):
        w, h = self.size
        img = np.full((h, w, 3), self.color, dtype=np.uint8)
        _put_center(img, self.msg_title, w / 2, h * 0.22, 1.0, BLANCO, 2, max_w=w - 20)
        for i, line in enumerate(self.lines):
            _put_center(img, line, w / 2, h * 0.42 + i * 32, 0.6, BLANCO, 1, max_w=w - 20)
        for b in self.buttons:
            b.draw(img)
        return img


class PinScreen(Screen):
    title = "PIN de administrador"

    def __init__(self, ui):
        super().__init__(ui)
        self.pin = ""
        self.error = ""
        w, h = self.size
        top, bw, bh = 82, w // 4, (h - 82) // 4
        keys = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Borrar", "0", "OK"]
        for i, k in enumerate(keys):
            col, row = i % 3, i // 3
            color = ROJO if k == "Borrar" else VERDE if k == "OK" else AZUL
            self.buttons.append(Button(col * bw, top + row * bh, bw, bh, k, self._key(k), color, 0.8))
        self.buttons.append(Button(3 * bw, top, w - 3 * bw, bh * 4, "Salir", lambda: EXIT, GRIS))

    def _key(self, k):
        def act():
            if k == "Borrar":
                self.pin = self.pin[:-1]
            elif k == "OK":
                return self.ui.check_pin(self)
            elif len(self.pin) < 8:
                self.pin += k
            self.error = ""
            return KEEP
        return act

    def draw_body(self, img):
        w, _ = self.size
        if self.error:
            _put(img, self.error, 10, 68, 0.55, (90, 90, 255), 1, max_w=w - 20)
        else:
            _put(img, "PIN: " + "*" * len(self.pin), 10, 70, 0.8, BLANCO, 2)


class MenuScreen(Screen):
    title = "Administracion"

    def __init__(self, ui):
        super().__init__(ui)
        w, h = self.size
        bw, bh, top = w // 2, (h - 44) // 2, 44
        self.buttons = [
            Button(0, top, bw, bh, "Nueva persona", lambda: KeyboardScreen(ui), VERDE, 0.7),
            Button(bw, top, w - bw, bh, "Personas", lambda: PeopleScreen(ui), AZUL, 0.7),
            Button(0, top + bh, bw, h - top - bh, "Entrenar modelo", self._train, AZUL, 0.7),
            Button(bw, top + bh, w - bw, h - top - bh, "Salir", lambda: EXIT, GRIS, 0.7),
        ]

    def _train(self):
        return self.ui.train_and_report(lambda: MenuScreen(self.ui))


class KeyboardScreen(Screen):
    """Teclado en pantalla para escribir el nombre de la persona."""
    title = "Nombre de la persona"
    ROWS = ["QWERTYUIOP", "ASDFGHJKLN", "ZXCVBNM"]

    def __init__(self, ui):
        super().__init__(ui)
        self.text = ""
        self.error = ""
        w, h = self.size
        top = 84
        kh = (h - top) // 4
        kw = w / 10
        for r, row in enumerate(self.ROWS):
            for c, ch in enumerate(row):
                label = "N~" if (r == 1 and ch == "N") else ch
                char = "Ñ" if label == "N~" else ch
                self.buttons.append(Button(int(c * kw), top + r * kh, int(kw), kh, label,
                                           self._typer(char), AZUL, 0.65))
        # fila 3: Z..M ocupan 7 teclas, borrar ocupa 3
        self.buttons.append(Button(int(7 * kw), top + 2 * kh, w - int(7 * kw), kh, "Borrar",
                                   self._backspace, ROJO, 0.6))
        y = top + 3 * kh
        self.buttons += [
            Button(0, y, int(3 * kw), h - y, "Cancelar", lambda: MenuScreen(ui), GRIS, 0.6),
            Button(int(3 * kw), y, int(4 * kw), h - y, "Espacio", self._typer(" "), AZUL, 0.6),
            Button(int(7 * kw), y, w - int(7 * kw), h - y, "Siguiente", self._ok, VERDE, 0.6),
        ]

    def _typer(self, ch):
        def act():
            if len(self.text) < 40 and not (ch == " " and (not self.text or self.text.endswith(" "))):
                # Primera letra de cada palabra en mayúscula, resto minúscula
                self.text += ch if (not self.text or self.text.endswith(" ")) else ch.lower()
            self.error = ""
            return KEEP
        return act

    def _backspace(self):
        self.text = self.text[:-1]
        return KEEP

    def _ok(self):
        name = self.text.strip()
        if len(name) < 2:
            self.error = "Escribe al menos 2 letras"
            return KEEP
        pid = people_service.create_person(name)
        return self.ui.start_capture(pid, name)

    def draw_body(self, img):
        w, _ = self.size
        cv2.rectangle(img, (6, 46), (w - 6, 80), (20, 20, 20), -1)
        if self.error:
            _put(img, self.error, 12, 70, 0.6, (90, 90, 255), 1)
        else:
            _put(img, (self.text or "") + "_", 12, 71, 0.7, BLANCO, 2, max_w=w - 24)


class PeopleScreen(Screen):
    title = "Personas"
    PER_PAGE = 4

    def __init__(self, ui, page: int = 0):
        super().__init__(ui)
        self.people = people_service.list_people()
        pages = max(1, (len(self.people) + self.PER_PAGE - 1) // self.PER_PAGE)
        self.page = min(max(0, page), pages - 1)
        w, h = self.size
        foot = 56
        rh = (h - 44 - foot) // self.PER_PAGE
        for i, p in enumerate(self.people[self.page * self.PER_PAGE:(self.page + 1) * self.PER_PAGE]):
            label = f"{p['full_name']}  ({ESTADOS.get(p['status'], p['status'])}, {p['photos']} fotos)"
            color = AZUL if p["status"] == "active" else GRIS
            self.buttons.append(Button(0, 44 + i * rh, w, rh, label,
                                       self._open(p["id"]), color, 0.55))
        y = h - foot
        self.buttons += [
            Button(0, y, w // 3, foot, "< Anterior", lambda: PeopleScreen(ui, self.page - 1), GRIS),
            Button(w // 3, y, w // 3, foot, "Volver", lambda: MenuScreen(ui), GRIS),
            Button(2 * w // 3, y, w - 2 * w // 3, foot, "Siguiente >", lambda: PeopleScreen(ui, self.page + 1), GRIS),
        ]
        self.title = f"Personas ({len(self.people)})  pag {self.page + 1}/{pages}"

    def _open(self, pid):
        return lambda: PersonScreen(self.ui, pid)

    def draw_body(self, img):
        if not self.people:
            w, h = self.size
            _put_center(img, "No hay personas registradas", w / 2, h / 2 - 20, 0.6)


class PersonScreen(Screen):
    def __init__(self, ui, pid: str):
        super().__init__(ui)
        self.pid = pid
        self.person = people_service.get_person(pid) or {"full_name": "?", "status": "?", "photos": 0}
        self.title = self.person["full_name"]
        w, h = self.size
        top = 100
        bw, bh = w // 2, (h - top) // 2
        active = self.person["status"] == "active"
        self.buttons = [
            Button(0, top, bw, bh, "Tomar fotos" if active else "(activar primero)",
                   self._capture if active else (lambda: KEEP), VERDE if active else GRIS),
            Button(bw, top, w - bw, bh, "Suspender" if active else "Activar", self._toggle,
                   ROJO if active else VERDE),
            Button(0, top + bh, bw, h - top - bh, "Eliminar", self._confirm_delete, ROJO),
            Button(bw, top + bh, w - bw, h - top - bh, "Volver", lambda: PeopleScreen(ui), GRIS),
        ]

    def _capture(self):
        return self.ui.start_capture(self.pid, self.person["full_name"])

    def _toggle(self):
        new = "suspended" if self.person["status"] == "active" else "active"
        people_service.set_status(self.pid, new)
        return PersonScreen(self.ui, self.pid)

    def _confirm_delete(self):
        name = self.person["full_name"]

        def yes():
            self.ui.show_busy("Eliminando...", "y reentrenando el modelo")
            people_service.delete_person(self.pid)
            return MessageScreen(self.ui, "Eliminado", [name, "Sus fotos fueron borradas"],
                                 VERDE, lambda: PeopleScreen(self.ui))

        return ConfirmScreen(self.ui, f"Eliminar a {name}?", "Se borran sus fotos. No se puede deshacer.",
                             yes, lambda: PersonScreen(self.ui, self.pid))

    def draw_body(self, img):
        p = self.person
        _put(img, f"Estado: {ESTADOS.get(p['status'], p['status'])}", 12, 66, 0.6)
        _put(img, f"Fotos guardadas: {p['photos']}", 12, 90, 0.6)


class ConfirmScreen(Screen):
    def __init__(self, ui, question, detail, on_yes, on_no):
        super().__init__(ui)
        self.question, self.detail = question, detail
        w, h = self.size
        self.buttons = [
            Button(0, h - 90, w // 2, 90, "Si, eliminar", on_yes, ROJO, 0.7),
            Button(w // 2, h - 90, w - w // 2, 90, "No", on_no, GRIS, 0.7),
        ]

    def draw_body(self, img):
        w, h = self.size
        _put_center(img, self.question, w / 2, h * 0.28, 0.8, BLANCO, 2, max_w=w - 20)
        _put_center(img, self.detail, w / 2, h * 0.45, 0.5, BLANCO, 1, max_w=w - 20)


class CaptureScreen(Screen):
    """Vista en vivo de la sesión de captura: caja verde/naranja + contador + guía."""
    dynamic = True

    def __init__(self, ui, pid: str, name: str, session):
        super().__init__(ui)
        self.pid, self.name, self.ses = pid, name, session
        w, _ = self.size
        self.buttons = [Button(w - 110, 0, 110, 46, "Detener", self._stop, ROJO, 0.6)]

    def busy(self) -> bool:
        return self.ses.status == "running"

    def _stop(self):
        self.ses.request_stop()
        return KEEP

    def tick(self):
        snap = self.ses.snapshot()
        if snap["status"] == "running":
            return KEEP
        saved = snap["saved"]
        if saved >= MIN_PHOTOS_TO_TRAIN:
            return self.ui.train_and_report(
                lambda: PersonScreen(self.ui, self.pid),
                header=f"{self.name}: {saved} fotos nuevas",
            )
        return MessageScreen(
            self.ui, "Pocas fotos",
            [f"Solo {saved} fotos validas.", "Busca mas luz y acercate.", snap.get("error") or ""],
            ROJO, lambda: PersonScreen(self.ui, self.pid),
        )

    def render(self):
        from .tft_display import _fit_cover

        w, h = self.size
        data = self.ses.read_preview()
        frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR) if data else None
        img = _fit_cover(frame, w, h) if frame is not None else np.full((h, w, 3), FONDO, np.uint8)
        snap = self.ses.snapshot()
        cv2.rectangle(img, (0, h - 54), (w, h), NEGRO, -1)
        _put(img, f"{snap['saved']}/{snap['target']}  {snap['guidance']}", 8, h - 32, 0.55,
             BLANCO, 1, max_w=w - 16)
        _put(img, "Mira a la camara, mueve un poco la cabeza", 8, h - 10, 0.45, (200, 200, 200), 1,
             max_w=w - 16)
        _put(img, self.name, 8, 28, 0.6, BLANCO, 2, max_w=w - 130)
        for b in self.buttons:
            b.draw(img)
        return img


# ----------------------------------------------------------------- controlador

@dataclass
class AdminUI:
    fb: object  # tft_display.Framebuffer (o un falso en pruebas)
    screen: Screen | None = None
    last_activity: float = 0.0
    _fails: list = field(default_factory=list)
    _dirty: bool = True
    _last_draw: float = 0.0

    @property
    def width(self) -> int:
        return self.fb.size[0]

    @property
    def height(self) -> int:
        return self.fb.size[1]

    @property
    def active(self) -> bool:
        return self.screen is not None

    def open(self) -> None:
        self.last_activity = time.time()
        if not people_service.has_admin_pin():
            self.screen = MessageScreen(
                self, "Sin PIN configurado",
                ["En la Pi ejecuta:", "python -m device.cli tft-pin"],
                GRIS, lambda: EXIT,
            )
        else:
            self.screen = PinScreen(self)
        self._dirty = True

    def close(self) -> None:
        if self.screen and self.screen.busy():
            ses = getattr(self.screen, "ses", None)
            if ses:
                ses.request_stop()
        self.screen = None

    def _apply(self, result) -> None:
        if result is None or result == EXIT:
            self.close()
        elif result != KEEP:
            self.screen = result
        self._dirty = True

    def step(self, tap: tuple[int, int] | None) -> None:
        """Un ciclo del menú: toque, tareas en curso, inactividad y dibujo."""
        if self.screen is None:
            return
        now = time.time()
        if tap is not None:
            self.last_activity = now
            self._apply(self.screen.tap(*tap))
        if self.screen is not None:
            result = self.screen.tick()
            if result != KEEP:
                self._apply(result)
        if (self.screen is not None and not self.screen.busy()
                and now - self.last_activity > INACTIVITY_SECONDS):
            self.close()
        # redibujo periódico: recupera la imagen si la consola de texto del
        # sistema llegó a escribir encima del framebuffer
        if self.screen is not None and (self._dirty or self.screen.dynamic
                                        or now - self._last_draw > 2.0):
            self.fb.show(self.screen.render())
            self._dirty = False
            self._last_draw = now

    # --- acciones compartidas por varias pantallas ---

    def check_pin(self, pin_screen: PinScreen):
        now = time.time()
        self._fails = [t for t in self._fails if now - t < PIN_LOCK_SECONDS]
        if len(self._fails) >= PIN_MAX_FAILS:
            wait = int(PIN_LOCK_SECONDS - (now - self._fails[0])) + 1
            pin_screen.error = f"Bloqueado: espera {wait} s"
            pin_screen.pin = ""
            return KEEP
        if people_service.verify_admin_pin(pin_screen.pin):
            self._fails.clear()
            people_service.audit("tft_admin_login", None)
            return MenuScreen(self)
        self._fails.append(now)
        people_service.audit("tft_pin_failed", None)
        pin_screen.error = f"PIN incorrecto ({PIN_MAX_FAILS - len(self._fails)} intentos)"
        pin_screen.pin = ""
        return KEEP

    def show_busy(self, title: str, subtitle: str = "") -> None:
        w, h = self.width, self.height
        img = np.full((h, w, 3), GRIS, dtype=np.uint8)
        _put_center(img, title, w / 2, h * 0.42, 0.9, BLANCO, 2, max_w=w - 20)
        if subtitle:
            _put_center(img, subtitle, w / 2, h * 0.6, 0.55, BLANCO, 1, max_w=w - 20)
        self.fb.show(img)

    def start_capture(self, pid: str, name: str):
        try:
            ses = capture_session.start_session(pid, CAPTURE_TARGET)
        except capture_session.CaptureBusyError:
            return MessageScreen(self, "Camara ocupada", ["Hay otra captura en curso", "(panel web)"],
                                 ROJO, lambda: PersonScreen(self, pid))
        people_service.audit("faces_capture_start", f"person={pid}")
        return CaptureScreen(self, pid, name, ses)

    def train_and_report(self, next_screen: Callable, header: str = ""):
        self.show_busy("Entrenando modelo...", "puede tardar unos segundos")
        used = people_service.retrain()
        if used is None:
            return MessageScreen(self, "Sin fotos", ["No hay fotos para entrenar"], ROJO, next_screen)
        lines = [header] if header else []
        lines.append(f"Modelo entrenado con {used} fotos")
        return MessageScreen(self, "Listo", lines, VERDE, next_screen)
