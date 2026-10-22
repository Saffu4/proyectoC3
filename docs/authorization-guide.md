# Guía de autorización y calibración del umbral LBPH

## Cómo decide el sistema (`device/access_service.py`)

Orden exacto de cada comprobación:

1. **Detección** del rostro (Haar Cascade).
2. **Predicción** LBPH → (etiqueta, distancia). La distancia se compara contra
   `LBPH_THRESHOLD` (65.0 heredado del base). **No es una probabilidad.**
3. **Resolución** etiqueta → `face_profiles.model_label` → `person_id`.
4. **Estado** de la persona: `revoked`/`suspended` → denegado inmediato.
5. **Vigencia**: `expires_at` en el pasado → denegado.
6. **Rol**: debe existir un rol del persona con permiso `access.granted`.
7. **Política local**: si `SYNC_ENABLED` y la copia está vencida
   (`POLICY_MAX_AGE_HOURS`) → denegado por prudencia (`denied_internal_error`).
8. **Registro**: cada intento con `event_id` UUID y categoría detallada.

Nunca: desconocido→permiso, coincidencia→rol admin, error interno→grant.

## Categorías de decisión

| Categoría | Significado |
|---|---|
| `welcome` | Autorizado con rol vigente |
| `denied_unknown` | No se identificó con el umbral |
| `denied_wrong_label` | Etiqueta reconocida sin perfil activo (inconsistencia) |
| `denied_suspended` / `denied_revoked` / `denied_expired` | Estado de la persona |
| `denied_no_role` | Sin rol con `access.granted` |
| `denied_model` | Modelo ausente o corrupto |
| `denied_camera` | Sin frames de cámara |
| `denied_internal_error` | Fallo interno o política vencida |

## Calibración del umbral (obligatorio antes de confiar en él)

Las pruebas automatizadas usan imágenes sintéticas (dist≈5 mismo rostro,
dist≈41 extraño, umbral 20). Con rostros reales se comporta distinto, por eso
el valor inicial 65.0 (del base) hay que validar:

```bash
# 1. Por cada persona autorizada, pide que mire a la cámara 1 min.
device/.venv/bin/python - <<'PY'
from device import db, capture_service
import time
# - pide al usuario mirar cámara y corre un bucle: teórico no incluído aquí.
# El flujo rápido: usar la herramienta panel: Cámara en vivo → "Comprobar
# acceso ahora" varias veces y revisar "Dist. LBPH" en el historial.
PY
```

**Procedimiento manual recomendado:**

1. Panel → Cámara en vivo → *Comprobar acceso ahora* x10 con cada persona
   autorizada: anota las 10 distancias.
2. Repite con 3–5 personas NO registradas y con fotos/imágenes parecidas.
3. Mean(autorizado) y max(autorizado); min(desconocido).
4. Elige `LBPH_THRESHOLD` entre `max(autorizados)+margen` y `min(desconocidos)-margen`.
   Si las bandas se superponen, **no uses el sistema para seguridad real**;
   mejora la captura (más/luz/ángulos) o el modelo.
5. Fijar valor en `.env` (`LBPH_THRESHOLD=...`) y reiniciar el servicio.

## Roles y permisos

- `roles` + `permissions` + `role_permissions` en SQLite (y en Supabase).
- Semilla: `admin` → `access.granted` + `panel.admin`; `user` → `access.granted`.
- Reconocer un rostro jamás concede `admin`; el panel exige sesión
  administrativa independiente.
- Cambiar permisos de un rol surte efecto en la siguiente comprobación
  (sin reentrenar).
