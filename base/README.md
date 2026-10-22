# Código base original (SOLO LECTURA)

Contiene una copia de los scripts del proyecto original de la Raspberry Pi,
sin modificar, como referencia de la FASE 1 (inspección):

- `detector.py` — Flask + cámara en hilo + LBPH; **/panel se protegía solo
  con el estado del reconocimiento** (sin sesión administrativa).
- `registrar_rostro.py` — captura a `~/Desktop/rostros/autorizado/`:
  cara más grande, margen 15%, 200×200, equalizeHist, ritmo 0.4 s.
- `entrenar_modelo.py` — entrena UNA persona con **etiqueta fija 1**.
- `README_autorizacion_rostros.md` — guía original del usuario.

Al ejecutarse el `device.cli import-base`, estos archivos no se modifican y
el modelo original queda intacto en `~/Desktop/modelos/lbph.yml`.
No editar aquí: esto es la instantánea histórica del código base.
