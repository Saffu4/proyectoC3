
import cv2
import os
import time
import threading
from flask import Flask, Response, render_template_string, redirect

app = Flask(__name__)

CAMERA_ID = 0
WIDTH, HEIGHT = 640, 480

CASCADE = (
    "/usr/share/opencv4/haarcascades/"
    "haarcascade_frontalface_default.xml"
)
MODEL_PATH = os.path.expanduser("~/Desktop/modelos/lbph.yml")

# LBPH: distancia más baja suele indicar mayor similitud.
# Este valor es inicial; debe calibrarse con pruebas reales.
UMBRAL_LBPH = 65.0

detector = cv2.CascadeClassifier(CASCADE)
if detector.empty():
    raise RuntimeError("No se pudo cargar Haar Cascade")

if not hasattr(cv2, "face"):
    raise RuntimeError("Esta instalación de OpenCV no tiene cv2.face")

if not os.path.isfile(MODEL_PATH):
    raise FileNotFoundError(
        f"No existe {MODEL_PATH}. Ejecuta entrenar_modelo.py primero."
    )

modelo = cv2.face.LBPHFaceRecognizer_create()
modelo.read(MODEL_PATH)

app = Flask(__name__)

camara = None
frame_lock = threading.Lock()
latest_frame = None
running = True

estado_lock = threading.Lock()
ultimo_reconocimiento = 0.0
ultimo_nombre = "Sin rostro autorizado"
ultima_distancia = None

# La autorización expira si no se vuelve a reconocer la cara.
VENTANA_AUTORIZACION = 5.0


def captura():
    global camara, latest_frame
    global ultimo_reconocimiento, ultimo_nombre, ultima_distancia

    camara = cv2.VideoCapture(CAMERA_ID, cv2.CAP_V4L2)
    camara.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    camara.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    camara.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not camara.isOpened():
        print(f"ERROR: no se pudo abrir la webcam {CAMERA_ID}")
        return

    print("Reconocimiento facial iniciado.")

    while running:
        ok, frame = camara.read()
        if not ok:
            time.sleep(0.1)
            continue

        frame = cv2.resize(frame, (WIDTH, HEIGHT))
        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gris = cv2.equalizeHist(gris)

        caras = detector.detectMultiScale(
            gris,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(80, 80)
        )

        autorizado = False
        distancia_mostrada = None

        for (x, y, w, h) in caras:
            rostro = gris[y:y+h, x:x+w]
            rostro = cv2.resize(rostro, (200, 200))
            rostro = cv2.equalizeHist(rostro)

            etiqueta, distancia = modelo.predict(rostro)
            distancia_mostrada = float(distancia)

            if etiqueta == 1 and distancia < UMBRAL_LBPH:
                autorizado = True
                texto = "AUTORIZADO"
                color = (0, 220, 0)
            else:
                texto = "NO RECONOCIDO"
                color = (0, 0, 255)

            cv2.rectangle(
                frame, (x, y), (x+w, y+h), color, 2
            )
            cv2.putText(
                frame, texto, (x, max(y-10, 25)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2
            )

        ahora = time.time()

        with estado_lock:
            if autorizado:
                ultimo_reconocimiento = ahora
                ultimo_nombre = "Persona autorizada"
                ultima_distancia = distancia_mostrada
            elif len(caras) > 0:
                ultimo_nombre = "Rostro no reconocido"
                ultima_distancia = distancia_mostrada

            acceso_activo = (
                ahora - ultimo_reconocimiento
                <= VENTANA_AUTORIZACION
            )

        texto_estado = (
            "ACCESO AUTORIZADO"
            if acceso_activo else "ACCESO BLOQUEADO"
        )
        color_estado = (0, 220, 0) if acceso_activo else (0, 0, 255)

        cv2.putText(
            frame, texto_estado, (10, 30),
            cv2.FONT_HERSHEY_SIMPLEX, 0.7, color_estado, 2
        )

        with frame_lock:
            latest_frame = frame.copy()

        time.sleep(0.03)

    if camara is not None:
        camara.release()


@app.route("/")
def inicio():
    return render_template_string("""
    <!doctype html>
    <html lang="es">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>Acceso facial</title>
      <style>
        body {
          background:#101820; color:#fff;
          font-family:Arial,sans-serif;
          text-align:center; margin:24px;
        }
        img {
          width:100%; max-width:800px;
          border:2px solid #28d17c; border-radius:8px;
        }
        a {
          display:inline-block; padding:12px 18px;
          background:#238636; color:white;
          text-decoration:none; border-radius:8px;
        }
        #estado {font-size:1.2rem; margin:16px}
      </style>
    </head>
    <body>
      <h1>Reconocimiento facial</h1>
      <img src="/video_feed" alt="Video de la webcam">
      <div id="estado">Consultando estado...</div>
      <a href="/panel">Intentar entrar al panel</a>
      <script>
        async function actualizar() {
          try {
            const r = await fetch('/api/status', {cache:'no-store'});
            const d = await r.json();
            document.getElementById('estado').textContent =
              d.autorizado
              ? 'ACCESO AUTORIZADO'
              : 'ACCESO BLOQUEADO';
          } catch(e) {
            document.getElementById('estado').textContent =
              'No se pudo consultar el estado';
          }
        }
        actualizar();
        setInterval(actualizar, 1000);
      </script>
    </body>
    </html>
    """)


@app.route("/api/status")
def status():
    with estado_lock:
        activo = (
            time.time() - ultimo_reconocimiento
            <= VENTANA_AUTORIZACION
        )
        nombre = ultimo_nombre

    return {"autorizado": activo, "estado": nombre}


@app.route("/panel")
def panel():
    with estado_lock:
        activo = (
            time.time() - ultimo_reconocimiento
            <= VENTANA_AUTORIZACION
        )

    if not activo:
        return redirect("/")

    return render_template_string("""
    <!doctype html>
    <html lang="es">
    <head><meta charset="utf-8"><title>Panel protegido</title></head>
    <body style="font-family:Arial;text-align:center;margin:50px">
      <h1>Acceso autorizado</h1>
      <p>El sistema ha reconocido el rostro registrado.</p>
      <p>Esta es una página de demostración.</p>
      <a href="/">Volver a la cámara</a>
    </body>
    </html>
    """)


@app.route("/video_feed")
def video_feed():
    def generar():
        while True:
            with frame_lock:
                frame = (
                    latest_frame.copy()
                    if latest_frame is not None else None
                )

            if frame is None:
                time.sleep(0.1)
                continue

            ok, jpg = cv2.imencode(
                ".jpg", frame,
                [int(cv2.IMWRITE_JPEG_QUALITY), 75]
            )
            if not ok:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpg.tobytes() + b"\r\n"
            )

    return Response(
        generar(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


if __name__ == "__main__":
    hilo = threading.Thread(target=captura, daemon=True)
    hilo.start()

    try:
        app.run(
            host="0.0.0.0",
            port=5000,
            debug=False,
            threaded=True
        )
    finally:
        running = False
        hilo.join(timeout=2)
