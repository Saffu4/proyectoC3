# Revocar permisos / suspensión / vencimiento

## Casos y efectos inmediatos

| Acción | Estado | Efecto en la devolución |
|---|---|---|
| Suspender | `suspended` | DENIED (`denied_suspended`) en la siguiente comprobación |
| Revocar | `revoked` | DENIED persistente (`denied_revoked`) |
| Vencer | `expires_at` pasado | DENIED (`denied_expired`, comprobado en cada decisión) |
| Quitar rol con `access.granted` | — | DENIED (`denied_no_role`) |

En todos los casos **no hace falta reentrenar el modelo**: la decisión se toma
después del reconocimiento, consultando estado + roles + vigencia en SQLite.

## Desde el panel web

1. `Personas` → Ver detalles de la persona.
2. Botón **Suspender** (temporal) o **Revocar** (persistente); ambos piden
   confirmación y quedan en auditoría.
3. Los cambios causan efecto **de inmediato** en el servicio: la siguiente
   comprobación del rostro consulta la BD local actualizada.

El rol `admin` no se puede crear cara a cara de forma automática: reconocer
un rostro jamás otorga rol de administrador.

## Borrar por completo (con política de retención)

Cuando se **elimina** la persona se borran:

1. las imágenes faciales (`rostros/<person_id>/`, carpeta con permiso 0o700)
2. su `face_profile` (desaparece la etiqueta LBPH del modelo en el próximo
   entrenamiento — hasta reentrenar, la etiqueta huérfana será `denied_wrong_label`)
3. los roles asignados

Los `access_events` **se conservan** (con `person_id=NULL`) por auditoría y
retención legal.

## Sincronización remota

Con Supabase activado, tras pulsar revocar:

1. El cambio local obtiene `updated_at = ahora` (más reciente que el remoto).
2. La próxima sincronización **empuja** el estado `revoked` al servidor.
3. En dispositivos remotos, una política localizable obsoleta NUNCA reactiva
   un permiso revocado: en conflictos gana el estado más estricto
   (`revoked > suspended > active`) y `updated_at` más reciente.

## Comando rápido (sin web)

```bash
device/.venv/bin/python - <<'PY'
import sys
from device import db
PID = "<person_id"
db.execute("UPDATE people SET status='revoked', updated_at=datetime('now') WHERE id=?", (PID,))
print("Revocado:", PID)
PY
```
