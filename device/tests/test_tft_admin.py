"""Pruebas del menú de administración táctil (sin hardware)."""
from __future__ import annotations

import numpy as np
import pytest

from device import capture_session, config, db, people_service, tft_admin, tft_display
from device.app import app
from . import helpers


class FakeFB:
    def __init__(self, w=480, h=320):
        self.size = (w, h)
        self.shown = 0
        self.last = None

    def show(self, img):
        assert img.shape == (self.size[1], self.size[0], 3)
        self.shown += 1
        self.last = img


class FakeSession:
    def __init__(self, saved=20, status="done"):
        self.id = "s1"
        self._snap = {"saved": saved, "target": 20, "status": status, "guidance": "ok", "error": None}
        self.stopped = False

    @property
    def status(self):
        return self._snap["status"]

    def snapshot(self):
        return dict(self._snap)

    def read_preview(self):
        return None

    def request_stop(self):
        self.stopped = True


def press(ui: tft_admin.AdminUI, label: str):
    """Toca el centro del botón con esa etiqueta."""
    for b in ui.screen.buttons:
        if b.label == label:
            ui.step((b.x + b.w // 2, b.y + b.h // 2))
            return
    raise AssertionError(f"No hay botón '{label}' en {type(ui.screen).__name__}: "
                         f"{[b.label for b in ui.screen.buttons]}")


def type_pin(ui, pin):
    for d in pin:
        press(ui, d)
    press(ui, "OK")


@pytest.fixture()
def ui(device_env):
    return tft_admin.AdminUI(FakeFB())


# -------------------------------------------------------------------- PIN

def test_sin_pin_configurado_no_abre_menu(ui):
    ui.open()
    ui.step(None)
    assert isinstance(ui.screen, tft_admin.MessageScreen)
    press(ui, "OK")
    assert not ui.active


def test_pin_correcto_abre_menu_y_queda_en_auditoria(ui):
    people_service.set_admin_pin("2468")
    ui.open()
    type_pin(ui, "2468")
    assert isinstance(ui.screen, tft_admin.MenuScreen)
    assert db.query("SELECT actor FROM audit_log WHERE action='tft_admin_login'")[0]["actor"] == "pantalla"


def test_pin_incorrecto_bloquea_tras_5_intentos(ui):
    people_service.set_admin_pin("2468")
    ui.open()
    for _ in range(5):
        type_pin(ui, "1111")
    type_pin(ui, "2468")  # incluso el correcto queda bloqueado
    assert isinstance(ui.screen, tft_admin.PinScreen)
    assert "Bloqueado" in ui.screen.error


def test_pin_invalido_rechazado():
    with pytest.raises(ValueError):
        people_service.set_admin_pin("12")
    with pytest.raises(ValueError):
        people_service.set_admin_pin("abcd")


def test_api_no_expone_ni_permite_cambiar_el_pin(device_env):
    people_service.set_admin_pin("2468")
    c = app.test_client()
    token = helpers.login_admin(c)
    h = {"Authorization": f"Bearer {token}"}
    assert people_service.PIN_SETTING not in c.get("/api/settings", headers=h).get_json()
    assert c.patch("/api/settings", json={people_service.PIN_SETTING: "x"}, headers=h).status_code == 400


# ------------------------------------------------------ nueva persona completa

def test_nueva_persona_teclado_captura_y_entrena(ui, monkeypatch):
    people_service.set_admin_pin("2468")
    started = {}

    def fake_start(pid, target):
        started["pid"] = pid
        from device.capture_service import ensure_face_profile

        ensure_face_profile(pid)
        helpers.add_face_images(pid, [7, 7, 7, 7, 7, 7])  # "fotos tomadas"
        return FakeSession(saved=6)

    monkeypatch.setattr(capture_session, "start_session", fake_start)
    ui.open()
    type_pin(ui, "2468")
    press(ui, "Nueva persona")
    for ch in "ANA":
        press(ui, ch)
    press(ui, "Espacio")
    for ch in "MARIA":
        press(ui, ch)
    assert ui.screen.text == "Ana Maria"
    press(ui, "Siguiente")
    # la sesión falsa ya terminó: el siguiente ciclo entrena y muestra "Listo"
    ui.step(None)
    assert isinstance(ui.screen, tft_admin.MessageScreen)
    assert ui.screen.msg_title == "Listo"
    p = db.query("SELECT full_name, status FROM people WHERE id=?", (started["pid"],))[0]
    assert (p["full_name"], p["status"]) == ("Ana Maria", "active")
    assert get_trained()


def get_trained():
    from device.face_recognizer import get_recognizer

    return get_recognizer().is_trained()


def test_nombre_corto_no_crea_persona(ui):
    people_service.set_admin_pin("2468")
    ui.open()
    type_pin(ui, "2468")
    press(ui, "Nueva persona")
    press(ui, "A")
    press(ui, "Siguiente")
    assert "2 letras" in ui.screen.error
    assert db.query("SELECT COUNT(*) AS c FROM people")[0]["c"] == 0


def test_pocas_fotos_no_entrena(ui, monkeypatch):
    pid = people_service.create_person("Beto")
    monkeypatch.setattr(capture_session, "start_session", lambda p, t: FakeSession(saved=2))
    ui.screen = ui.start_capture(pid, "Beto")
    ui.last_activity = __import__("time").time()
    ui.step(None)
    assert ui.screen.msg_title == "Pocas fotos"


# ------------------------------------------------------------ gestionar persona

def _goto_person(ui, name):
    people_service.set_admin_pin("2468")
    ui.open()
    type_pin(ui, "2468")
    press(ui, "Personas")
    for b in ui.screen.buttons:
        if b.label.startswith(name):
            ui.step((b.x + 5, b.y + 5))
            return
    raise AssertionError("persona no listada")


def test_suspender_y_activar_desde_pantalla(ui):
    pid = people_service.create_person("Carla Ruiz")
    _goto_person(ui, "Carla Ruiz")
    press(ui, "Suspender")
    assert db.query("SELECT status FROM people WHERE id=?", (pid,))[0]["status"] == "suspended"
    press(ui, "Activar")
    assert db.query("SELECT status FROM people WHERE id=?", (pid,))[0]["status"] == "active"


def test_eliminar_pide_confirmacion(ui):
    pid = people_service.create_person("Dora Paz")
    helpers.add_face_images(pid, [3, 3, 3])
    _goto_person(ui, "Dora Paz")
    press(ui, "Eliminar")
    press(ui, "No")
    assert db.query("SELECT COUNT(*) AS c FROM people")[0]["c"] == 1
    press(ui, "Eliminar")
    press(ui, "Si, eliminar")
    assert db.query("SELECT COUNT(*) AS c FROM people")[0]["c"] == 0
    assert db.query("SELECT COUNT(*) AS c FROM face_profiles")[0]["c"] == 0


def test_inactividad_cierra_el_menu(ui, monkeypatch):
    people_service.set_admin_pin("2468")
    ui.open()
    type_pin(ui, "2468")
    ui.last_activity -= tft_admin.INACTIVITY_SECONDS + 1
    ui.step(None)
    assert not ui.active


def test_todas_las_pantallas_dibujan_en_horizontal_y_vertical(device_env):
    pid = people_service.create_person("Eva Lopez")
    for w, h in ((480, 320), (320, 480)):
        ui = tft_admin.AdminUI(FakeFB(w, h))
        screens = [
            tft_admin.PinScreen(ui), tft_admin.MenuScreen(ui), tft_admin.KeyboardScreen(ui),
            tft_admin.PeopleScreen(ui), tft_admin.PersonScreen(ui, pid),
            tft_admin.ConfirmScreen(ui, "Eliminar?", "detalle", lambda: None, lambda: None),
            tft_admin.MessageScreen(ui, "Listo", ["linea"]),
            tft_admin.CaptureScreen(ui, pid, "Eva", FakeSession(status="running")),
        ]
        for s in screens:
            assert s.render().shape == (h, w, 3)


# --------------------------------------------- integración con la vista TFT

def test_boton_admin_en_vista_abre_pin(device_env, tmp_path, monkeypatch):
    people_service.set_admin_pin("2468")
    monkeypatch.setattr(config, "TFT_TOUCH_CAL", "0,480,0,320,0")  # crudo = pantalla
    helpers.set_camera_static([helpers.make_test_frame(1)])

    class Touch:
        device = "x"
        taps = [(470, 10)]  # esquina superior derecha

        def pop_tap(self):
            return self.taps.pop() if self.taps else None

    class NoFace:
        def detect(self, f):
            return []

    fb = FakeFB()
    disp = tft_display.TFTDisplay(fb, Touch(), detector=NoFace())
    disp.step()
    assert isinstance(disp.admin.screen, tft_admin.PinScreen)
    assert db.query("SELECT COUNT(*) AS c FROM access_events")[0]["c"] == 0  # no verificó acceso


def test_captura_interactiva_crea_perfil_facial(device_env):
    """Antes la sesión del panel web guardaba fotos SIN perfil: nunca se entrenaban."""
    pid = people_service.create_person("Fabio")
    helpers.set_camera_static([helpers.make_test_frame(1)])
    ses = capture_session.start_session(pid, 1)
    ses.request_stop()
    assert db.query("SELECT COUNT(*) AS c FROM face_profiles WHERE person_id=?", (pid,))[0]["c"] == 1


# --------------------------------------------------------------- calibración

def test_calibracion_recupera_valores(device_env):
    real = tft_display.TouchCalibration(3936, 227, 268, 3880, True)
    w, h = 480, 320

    def raw_for(sx, sy):  # inverso de to_screen con swap
        x = real.xmin + sx / w * (real.xmax - real.xmin)
        y = real.ymin + sy / h * (real.ymax - real.ymin)
        return (round(y), round(x))  # swap: crudo_x da la Y, crudo_y da la X

    pts = [((30, 30), raw_for(30, 30)), ((450, 30), raw_for(450, 30)), ((30, 290), raw_for(30, 290))]
    cal = tft_display.compute_calibration(pts, w, h)
    assert cal.swap is True
    for sx, sy in ((30, 30), (240, 160), (450, 290)):
        x, y = cal.to_screen(*raw_for(sx, sy), w, h)
        assert abs(x - sx) <= 2 and abs(y - sy) <= 2


def test_guardar_valor_en_env(tmp_path):
    env = tmp_path / ".env"
    env.write_text("A=1\nTFT_TOUCH_CAL=viejo\n")
    tft_display.save_env_value("TFT_TOUCH_CAL", "1,2,3,4,0", env)
    assert env.read_text() == "A=1\nTFT_TOUCH_CAL=1,2,3,4,0\n"
