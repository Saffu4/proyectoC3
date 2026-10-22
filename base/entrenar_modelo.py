
import cv2
import os
import glob
import numpy as np

CARPETA = os.path.expanduser("~/Desktop/rostros/autorizado")
SALIDA = os.path.expanduser("~/Desktop/modelos/lbph.yml")

if not hasattr(cv2, "face"):
    raise RuntimeError(
        "OpenCV no tiene cv2.face. "
        "Comprueba la instalación de opencv-contrib."
    )

archivos = glob.glob(os.path.join(CARPETA, "*.jpg"))

if len(archivos) < 10:
    raise RuntimeError(
        f"Solo hay {len(archivos)} imágenes. "
        "Registra al menos 10; se recomiendan 30-40."
    )

imagenes = []
etiquetas = []

for archivo in archivos:
    imagen = cv2.imread(archivo, cv2.IMREAD_GRAYSCALE)

    if imagen is None:
        continue

    imagen = cv2.resize(imagen, (200, 200))
    imagen = cv2.equalizeHist(imagen)

    imagenes.append(imagen)
    etiquetas.append(1)

if len(imagenes) < 10:
    raise RuntimeError("No hay suficientes imágenes válidas.")

modelo = cv2.face.LBPHFaceRecognizer_create()
modelo.train(imagenes, np.array(etiquetas, dtype=np.int32))

os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
modelo.write(SALIDA)

print("Modelo entrenado correctamente.")
print("Imágenes utilizadas:", len(imagenes))
print("Archivo:", SALIDA)
print("Etiqueta 1: persona autorizada")
