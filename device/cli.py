"""CLI del dispositivo.

Uso (desde la raíz del proyecto en la Pi):
  python -m device.cli init-admin --username admin --password '...'
  python -m device.cli train
  python -m device.cli access-check        # una comprobación de acceso en vivo
  python -m device.cli capture --person-id UUID --count 10
  python -m device.cli serve               # arranca Flask (no exponer a Internet)
  python -m device.cli tft-test            # probar la pantalla TFT y el táctil
  python -m device.cli tft                 # solo la vista de acceso en la TFT
  python -m device.cli tft-pin             # PIN del menú Admin de la pantalla
  python -m device.cli tft-calibrar        # calibrar el táctil (3 toques)
"""
from __future__ import annotations

import argparse

from . import config, db
from .auth import init_admin
from .camera import get_source, set_source, StaticSource, NoCameraSource
from .capture_service import capture_faces
from .face_detector import FaceDetector
from .face_recognizer import get_recognizer, load_face_to_train

import cv2


def cmd_import_base(args):
    """Migra el proyecto base a la nueva estructura SIN tocar los archivos originales.

    Importa las imágenes de ~/Desktop/rostros/autorizado (o la ruta dada) como
    la primera persona (model_label=1, compatible con el modelo base), traslada
    usa copia el modelo lbph.yml existente al almacén privado y entrena desde cero.
    Los archivos originales permanecen intactos: aquí solo se COPIA."""
    import shutil
    import glob
    import os

    from device import capture_service

    db.init_db()
    src = os.path.expanduser(args.src)
    images = sorted(glob.glob(os.path.join(src, "*.jpg")))
    if not images:
        raise SystemExit(f"[error] No se encontraron *.jpg en {src}")
    if not args.force and db.query("SELECT 1 FROM people WHERE full_name = ?", (args.name,)):
        raise SystemExit(
            f"[error] Ya existe una persona llamada '{args.name}' (¿import-base ya se ejecutó?). "
            "Usa --name con otro nombre o --force para importarla de nuevo."
        )
    pid =capture_service.ensure_face_profile_person(
        full_name=args.name, document_id=None, roles=("user",),
        status="active", expires_at=None,
    )
    folder = config.faces_dir(pid)
    config.ensure_data_dirs()
    folder.mkdir(parents=True, exist_ok=True)
    copied = 0
    for img_path in images:
        im = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        normal = load_face_to_train(im)
        out = folder / f"migrada_{copied + 1:03d}.jpg"
        cv2.imwrite(str(out), normal)
        copied += 1
    if copied == 0:
        raise SystemExit("[error] Ninguna imagen se pudo leer")
    used = get_recognizer().train()
    labels = db.query(
        "SELECT p.full_name, f.model_label FROM face_profiles f JOIN people p ON p.id=f.person_id"
    )
    print(f"[ok] {copied}/{len(images)} imágenes migradas (persona '{args.name}').")
    print(f"[ok] Modelo entrenado con {used} imágenes:")
    for r in labels:
        print(f"  label={r['model_label']} -> {r['full_name']}")
    if args.model:
        model_src = os.path.expanduser(args.model)
        if os.path.isfile(model_src):
            shutil.copy2(model_src, config.models_dir() / "modelo_lbph_base_csv.bak.yml")
            print(f"[ok] Modelo base respaldado en copia PRIVADA (no en Git): modelo_lbph_base_csv.bak.yml")


def cmd_init_admin(args):
    db.init_db()  # permite ejecutar init-admin en una instalación nueva
    init_admin(args.username, args.password)
    print(f"[ok] Cuenta administrativa '{args.username}' creada/actualizada.")


def cmd_train(_args):
    db.init_db()
    used = get_recognizer().train()
    labels = db.query("SELECT model_label, person_id FROM face_profiles ORDER BY model_label")
    print(f"[ok] Modelo entrenado con {used} imágenes. Mapa de etiquetas:")
    for r in labels:
        print(f"  label={r['model_label']} -> persona={r['person_id']}")


def cmd_access_check(_args):
    db.init_db()
    detector = FaceDetector()
    recognizer = get_recognizer()
    frame = get_source().read()
    faces = detector.detect(frame)
    if not faces:
        print("[denied] No se detectó ningún rostro")
        return
    from . import access_service
    from .face_recognizer import crop_face

    match = recognizer.predict(crop_face(frame, faces[0]))
    decision = access_service.decide_from_recognition(match)
    state = "GRANTED" if decision.granted else "DENIED"
    print(f"[{state}] category={decision.category} person={decision.person_id} "
          f"dists={decision.confidence} motivo={decision.reason}")


def cmd_capture(args):
    db.init_db()
    result = capture_faces(args.person_id, count=args.count)
    print(f"[ok] Guardados {result['saved']} rostros (model_label={result['model_label']})")


def cmd_serve(args):
    db.init_db()
    from .app import app

    if config.TFT_ENABLED:
        from . import tft_display

        tft_display.start_in_thread()  # misma cámara que la API (un solo proceso)

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,  # nunca debug expuesto
        threaded=True,
    )


def cmd_tft(_args):
    """Solo la vista de acceso en la pantalla TFT (sin API web)."""
    db.init_db()
    from . import tft_display

    display = tft_display.build_display()
    print(f"[tft] Vista de acceso en {display.fb.info.device}. Ctrl+C para salir.")
    try:
        display.run()
    except KeyboardInterrupt:
        display.stop()


def cmd_tft_test(args):
    """Barras de color + coordenadas del táctil, para comprobar la instalación."""
    from . import tft_display

    tft_display.patron_prueba(seconds=args.segundos)


def cmd_tft_pin(args):
    """Configura el PIN numérico del menú de administración de la pantalla."""
    import getpass

    from . import people_service

    db.init_db()
    pin = args.pin
    if not pin:
        pin = getpass.getpass("Nuevo PIN (4 a 8 dígitos): ")
        if getpass.getpass("Repite el PIN: ") != pin:
            raise SystemExit("[error] Los PIN no coinciden")
    try:
        people_service.set_admin_pin(pin)
    except ValueError as exc:
        raise SystemExit(f"[error] {exc}")
    print("[ok] PIN de la pantalla guardado. Úsalo en el botón 'Admin' de la pantalla.")


def cmd_tft_calibrar(_args):
    """Calibra el táctil tocando 3 cruces; guarda TFT_TOUCH_CAL en .env."""
    from . import tft_display

    tft_display.calibrar()


def main():
    parser = argparse.ArgumentParser(description="CLI del dispositivo proyectoC3")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init-admin", help="crear el primer administrador (SOLO inicialización)")
    p.add_argument("--username", default="admin")
    p.add_argument("--password", required=True)
    p.set_defaults(func=cmd_init_admin)

    p = sub.add_parser("import-base", help="migrar el proyecto base (copiar rostros/modelo)")
    p.add_argument("--src", default="~/Desktop/rostros/autorizado",
                   help="carpeta del base con los .jpg de la persona autorizada")
    p.add_argument("--name", default="Persona autorizada")
    p.add_argument("--model", default="~/Desktop/modelos/lbph.yml",
                   help="modelo lbph.yml del base (solo se respalda una copia)")
    p.add_argument("--force", action="store_true",
                   help="importar aunque ya exista una persona con ese nombre")
    p.set_defaults(func=cmd_import_base)

    p = sub.add_parser("train", help="entrenar el modelo LBPH")
    p.set_defaults(func=cmd_train)

    p = sub.add_parser("access-check", help="comprobación de acceso en vivo")
    p.add_argument("--camera", default=None, help="webcam|none")
    p.set_defaults(func=cmd_access_check)

    p = sub.add_parser("capture", help="capturar rostros de una persona")
    p.add_argument("--person-id", required=True)
    p.add_argument("--count", type=int, default=10)
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("tft", help="vista de acceso en la pantalla TFT (sin API web)")
    p.set_defaults(func=cmd_tft)

    p = sub.add_parser("tft-test", help="probar pantalla TFT y táctil (barras de color)")
    p.add_argument("--segundos", type=float, default=60.0)
    p.set_defaults(func=cmd_tft_test)

    p = sub.add_parser("tft-pin", help="configurar el PIN del menú Admin de la pantalla")
    p.add_argument("--pin", default=None, help="si se omite, se pide sin mostrarlo")
    p.set_defaults(func=cmd_tft_pin)

    p = sub.add_parser("tft-calibrar", help="calibrar el táctil de la pantalla (3 toques)")
    p.set_defaults(func=cmd_tft_calibrar)

    p = sub.add_parser("serve", help="arrancar la API/panel (localhost)")
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
