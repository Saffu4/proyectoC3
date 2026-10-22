# Registrar una persona (flujo administrativo)

## 1. Desde el panel web

1. Inicia sesión en el panel (`/login`) con la cuenta creada por `init-admin`.
2. Personas → ** Registrar persona**:
   - nombre completo (visible en la pantalla de bienvenida SOLO su primer nombre)
   - identificador/documento (opcional)
   - vigencia: fecha de vencimiento o vacío (sin vencimiento)
   - rol: `user` o `admin`
3. Al crear la persona el sistema le asigna un `person_id` UUID; el estado
   empieza `active` pero **no puede acceder hasta tener imágenes entrenadas
   y el rol con el permiso `access.granted`**.
4. En la ficha de la persona ("Ver detalles"):
   - **Capturar**: captura ≥10 rostros de la webcam activa (mismo pipeline
     del base: cara más grande, margen 15%, 200×200, equalizeHist).
     Personas en distintos encuadres: separadas automáticamente; si se
     interrumpe, reintenta.
   - **Reentrenar modelo**: reconstruye `modelo_lbph.yml` con las imágenes de
     TODAS las personas con perfil habilitado. Comprobación previa: si hay
     etiquetas duplicadas en `face_profiles`, se cancela con error 409.
5. Prueba: si la persona va a abrir la puerta del panel, haz una
   `Comprobar acceso ahora` en Cámara en vivo para ver la decisión y el
   evento registrado en Historial.
6. Auditar: todas las acciones quedan en `audit_log` (persona creada,
   suspendida, revocada, entrenada, etc.).

## 2. Línea de comandos (alternativa)

```bash
# crear persona (id UUID saldrá en la salida; guarda el primer pid)
python -c "from device import db; db.init_db()"   # asegura el schema
device/.venv/bin/python -m device.cli capture --person-id <UUID> --count 10
device/.venv/bin/python -m device.cli train
device/.venv/bin/python -m device.cli access-check   # comprobación en vivo
```

## 3. Verificaciones del flujo (garantías)

- La captura **solo acepta personas `active`** (nunca suspendidas/revocadas).
- La etiqueta `model_label` es única e incremental (`max+1`): reentrenar
  NUNCA reasigna la etiqueta de otra persona.
- El permiso se rehace con estado `active`, vencimiento válido, rol con
  `access.granted` y copia de política fresca (si sync está activada).
- Las imágenes viven en `{PROYECTO_C3_DATA}/rostros/<person_id>/` con
  permiso 0o700, jamás en el repositorio.

## 4. Consentimiento (obligatorio en producción)

Antes de incluir el rostro: pedir consentimiento explícito por escrito,
especificando propósito, retención y cómo pedir su eliminación. Ver
`docs/security.md` para la política de retención.
