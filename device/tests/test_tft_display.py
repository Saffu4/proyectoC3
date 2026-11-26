"""Pruebas de la vista de acceso en la pantalla TFT (sin hardware: framebuffer
simulado con un archivo, sysfs y /proc falsos, eventos táctiles sintéticos)."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest

from device import config, db, tft_display
from device.face_recognizer import get_recognizer, invalidate_shared
from . import helpers

W, H = 480, 320


def _fake_sysfs(root: Path, name="fb_ili9486", fb="fb1", size="480,320", bpp="16") -> None:
    d = root / fb
    d.mkdir(parents=True)
    (d / "name").write_text(name + "\n")
    (d / "virtual_size").write_text(size + "\n")
    (d / "bits_per_pixel").write_text(bpp + "\n")
    (d / "stride").write_text(str(int(size.split(",")[0]) * int(bpp) // 8) + "\n")


def _fake_fb(tmp_path: Path) -> tft_display.Framebuffer:
    dev = tmp_path / "fb1"
    dev.write_bytes(b"\0" * W * H * 2)
    return tft_display.Framebuffer(tft_display.FramebufferInfo(str(dev), W, H, 16, W * 2))


class FaceEverywhere:
    """Detector falso: un 'rostro' que ocupa todo el fotograma."""

    def detect(self, frame):
        h, w = frame.shape[:2]
        return [(0, 0, w, h)]


class NoFace:
    def detect(self, frame):
        return []


class FakeTouch:
    device = "/dev/input/event-falso"

    def __init__(self):
        self.taps = []

    def pop_tap(self):
        return self.taps.pop() if self.taps else None


# ------------------------------------------------------------ descubrimiento

def test_detecta_framebuffer_ili9486(device_env, tmp_path):
    root = tmp_path / "graphics"
    _fake_sysfs(root, name="vc4drmfb", fb="fb0", size="1920,1080", bpp="32")
    _fake_sysfs(root, name="fb_ili9486", fb="fb1")
    info = tft_display.find_framebuffer(str(root), "/dev")
    assert (info.device, info.width, info.height, info.bpp) == ("/dev/fb1", 480, 320, 16)


def test_sin_pantalla_da_error_claro(device_env, tmp_path):
    root = tmp_path / "graphics"
    _fake_sysfs(root, name="vc4drmfb", fb="fb0")
    with pytest.raises(tft_display.TFTNotFoundError, match="instalar_pantalla_tft"):
        tft_display.find_framebuffer(str(root))


def test_detecta_tactil_ads7846(device_env, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TFT_TOUCH_DEVICE", "")
    proc = tmp_path / "devices"
    proc.write_text(
        'I: Bus=0003\nN: Name="Logitech USB Keyboard"\nH: Handlers=sysrq kbd event0\n\n'
        'I: Bus=001c\nN: Name="ADS7846 Touchscreen"\nH: Handlers=mouse0 event3\n\n'
    )
    assert tft_display.find_touch_device(str(proc)) == "/dev/input/event3"


# ------------------------------------------------------------------- píxeles

def test_rgb565():
    img = np.array([[[0, 0, 255], [0, 255, 0], [255, 0, 0], [255, 255, 255]]], dtype=np.uint8)
    assert tft_display.bgr_to_rgb565(img).tolist() == [[0xF800, 0x07E0, 0x001F, 0xFFFF]]


def test_framebuffer_escribe_tamano_correcto(tmp_path):
    fb = _fake_fb(tmp_path)
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:, :] = (0, 0, 255)  # rojo
    fb.show(img)
    data = Path(fb.info.device).read_bytes()
    assert len(data) == W * H * 2
    assert struct.unpack_from("<H", data, 0)[0] == 0xF800


def test_render_ajusta_a_pantalla():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert tft_display.render_live(frame, W, H, "Toca").shape == (H, W, 3)
    assert tft_display.render_live(frame, 320, 480, "Toca").shape == (480, 320, 3)  # vertical
    img = tft_display.render_decision(W, H, False, "denied_revoked", None)
    assert tuple(img[5, 5]) == tft_display.ROJO


# -------------------------------------------------------------------- táctil

def _ev(etype, code, value):
    return struct.pack("llHHi", 0, 0, etype, code, value)


def test_toque_se_registra_al_levantar_el_dedo():
    t = tft_display.TouchReader("/dev/null")
    st: dict = {}
    t.feed(_ev(3, 0, 1000) + _ev(3, 1, 2000) + _ev(1, 0x14A, 1), st)
    assert t.pop_tap() is None  # aún presionado
    t.feed(_ev(3, 0, 1100) + _ev(1, 0x14A, 0), st)
    assert t.pop_tap() == (1100, 2000)
    assert t.pop_tap() is None


def test_calibracion_con_ejes_intercambiados():
    cal = tft_display.TouchCalibration.parse("3936,227,268,3880,1")
    # swap: x de pantalla sale del eje Y crudo (invertido), y de pantalla del X crudo
    assert cal.to_screen(268, 3936, W, H) == (0, 0)
    assert cal.to_screen(3880, 227, W, H) == (W - 1, H - 1)


# -------------------------------------------------- comprobación real (con log)

def _trained_person(name="Ana Prueba"):
    pid = helpers.create_person(name)
    helpers.add_face_images(pid, [1, 1, 1])
    get_recognizer().train()
    invalidate_shared()
    return pid


def test_toque_hace_comprobacion_real_y_registra(device_env, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TFT_MODE", "toque")
    monkeypatch.setattr(config, "TFT_LIVE_RECOGNITION", False)
    pid = _trained_person()
    helpers.set_camera_static([helpers.make_test_frame(1)])
    touch = FakeTouch()
    disp = tft_display.TFTDisplay(_fake_fb(tmp_path), touch, detector=FaceEverywhere())

    disp.step()  # vista en vivo: no registra nada
    assert db.query("SELECT COUNT(*) AS c FROM access_events")[0]["c"] == 0

    touch.taps.append((2000, 2000))
    disp.step()
    ev = db.query("SELECT person_id, result, category FROM access_events")
    assert [(e["person_id"], e["result"], e["category"]) for e in ev] == [(pid, "granted", "welcome")]


def test_toque_persona_revocada_denegada(device_env, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TFT_MODE", "toque")
    pid = _trained_person()
    db.execute("UPDATE people SET status='revoked' WHERE id=?", (pid,))
    helpers.set_camera_static([helpers.make_test_frame(1)])
    res = tft_display.run_access_check(FaceEverywhere())
    assert (res.granted, res.category) == (False, "denied_revoked")


def test_sin_rostro_no_registra(device_env):
    helpers.set_camera_static([helpers.make_test_frame(1)])
    res = tft_display.run_access_check(NoFace())
    assert (res.granted, res.category) == (False, "no_face")
    assert db.query("SELECT COUNT(*) AS c FROM access_events")[0]["c"] == 0


def test_camara_desconectada_no_rompe(device_env, tmp_path):
    helpers.set_camera_disconnected()
    disp = tft_display.TFTDisplay(_fake_fb(tmp_path), FakeTouch(), detector=NoFace())
    disp.step()  # muestra "Camara desconectada" sin lanzar excepción
    assert tft_display.run_access_check(NoFace()).category == "camera"


def test_modo_auto_verifica_con_rostro_estable(device_env, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TFT_MODE", "auto")
    monkeypatch.setattr(config, "TFT_FPS", 3)
    monkeypatch.setattr(config, "TFT_LIVE_RECOGNITION", False)
    _trained_person()
    helpers.set_camera_static([helpers.make_test_frame(1)])
    disp = tft_display.TFTDisplay(_fake_fb(tmp_path), None, detector=FaceEverywhere())
    for _ in range(3):
        disp.step()
    assert db.query("SELECT COUNT(*) AS c FROM access_events WHERE result='granted'")[0]["c"] == 1
    disp.step()  # durante el resultado/cooldown no se repite
    assert db.query("SELECT COUNT(*) AS c FROM access_events")[0]["c"] == 1


def test_swap_rb_corrige_colores(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TFT_SWAP_RB", True)
    fb = _fake_fb(tmp_path)
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[:, :] = (0, 0, 255)  # rojo en BGR -> se envía como azul
    fb.show(img)
    assert struct.unpack_from("<H", Path(fb.info.device).read_bytes(), 0)[0] == 0x001F


def test_arranque_espera_a_que_aparezca_la_pantalla(device_env, monkeypatch):
    """Al encender, el driver puede tardar: start_in_thread reintenta."""
    calls = {"n": 0}

    class Ready:
        class fb:
            class info:
                device, width, height = "/dev/fb1", 480, 320
        mode, touch = "toque", None

        def run(self):
            calls["ran"] = True

    def fake_build():
        calls["n"] += 1
        if calls["n"] < 3:
            raise tft_display.TFTNotFoundError("aún no")
        return Ready()

    monkeypatch.setattr(tft_display, "build_display", fake_build)
    t = tft_display.start_in_thread(wait_seconds=5, retry_every=0.01)
    t.join(2)
    assert calls["n"] == 3 and calls.get("ran")
