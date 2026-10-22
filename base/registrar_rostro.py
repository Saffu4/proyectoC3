
import cv2
import os
import time

CARPETA = os.path.expanduser("~/Desktop/rostros/autorizado")
os.makedirs(CARPETA, exist_ok=True)

CASCADE = (
    "/usr/share/opencv4/haarcascades/"
    "haarcascade_frontalface_default.xml"
)

detector = cv2.CascadeClassifier(CASCADE)
camara = cv2.VideoCapture(0, cv2.CAP_V4L2)

if not camara.isOpened():
    raise RuntimeError("No se pudo abrir la webcam USB")

guardadas = 0
maximo = 40
ultima = 0

print("Registro iniciado.")
print("Mira a la cámara y gira lentamente la cabeza.")
print("Se guardarán hasta 40 imágenes. Ctrl+C para cancelar.")

try:
    while guardadas < maximo:
        ok, frame = camara.read()
        if not ok:
            print("No se pudo leer la cámara.")
            time.sleep(0.2)
            continue

        gris = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        caras = detector.detectMultiScale(
            gris,
            scaleFactor=1.2,
            minNeighbors=5,
            minSize=(80, 80)
        )

        ahora = time.time()

        if len(caras) > 0 and ahora - ultima >= 0.4:
            # Registrar solo la cara más grande.
            x, y, w, h = max(caras, key=lambda c: c[2] * c[3])

            # Margen alrededor del rostro.
            margen_x = int(w * 0.15)
            margen_y = int(h * 0.15)
            x1 = max(0, x - margen_x)
            y1 = max(0, y - margen_y)
            x2 = min(gris.shape[1], x + w + margen_x)
            y2 = min(gris.shape[0], y + h + margen_y)

            rostro = gris[y1:y2, x1:x2]
            rostro = cv2.resize(rostro, (200, 200))
            rostro = cv2.equalizeHist(rostro)

            ruta = os.path.join(
                CARPETA, f"rostro_{guardadas + 1:03d}.jpg"
            )
            if cv2.imwrite(ruta, rostro):
                guardadas += 1
                ultima = ahora
                print(f"Imagen {guardadas}/{maximo} guardada")

        time.sleep(0.03)

except KeyboardInterrupt:
    print("\nRegistro cancelado.")

finally:
    camara.release()

print(f"Registro finalizado: {guardadas} imágenes.")
