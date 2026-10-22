# Seguridad y riesgos

## Modelo de amenaza resumido

| Riesgo | Mitigación en proyectoC3 |
|---|---|
| Robo del modelo/rostros por leak de repo | Datos en `{PROYECTO_C3_DATA}` (0o700, fuera de Git); `.gitignore` estricto (`rostros/`, `modelos/`, `*.db`, backups) |
| Suplantación con foto/imagen impresa | LBPH es 2D: **no garantiza prueba de vida**. Ver riesgos_accepted, fase sugerida abajo |
| Panel desprotegido | Sesiones administrativas reales (PBKDF2 + token TTL + rate-limit 5 intentos/60 s); cada endpoint valida en servidor |
| Cámara expuesta | `/api/camera/stream` exige sesión; nunca se abre puerto público |
| Roles enviados por el cliente | Ignorados: server-side siempre contra `admin_accounts` / SQLite |
| Primer admin impostado | Solo `device.cli init-admin` (local en la Pi, requiere SSH) |
| Doble sincronización de eventos | `event_id` UUID único + UPSERT por lado remoto |
| Copia local obsoleta reactiva revocación | Estado más estricto gana: `revoked > suspended > active`; nunca down-revquiet |

## Riesgos aceptados (documentar a los stakeholders)

1. **LBPH no es un sistema biométrico fuerte.** Es una demo de reconocimiento;
   puede fallar con iluminación extrema, gafas/peinado cambiado, común- gemelas.
   Umbral 65 = valor inicial del base; **calibrar** (authorization-guide.md).
2. **No hay prueba de vida (anti-spoofing)**: una foto mostrada al sensor puede
   engañarlo. Para escenarios sensibles, añadir `blink/liveness` (Out-of-scope),
   mano-ostruida, o combinar con tarjeta/PIN (alternativa manual SIEMPRE).
3. **Offline**: si la Pi pierde conexión largo, la copia local sigue permitiendo
   acceso de personas que estaban activas al último sync; stó luego las decisiones
   privilegiadas se bloquean si `POLICY_MAX_AGE_HOURS` vence con sync habilitada.
4. **Cookies/tokens** en `sessionStorage` del navegador: al cerrar pestaña se
   borra el token; es deliberado (sessiones cortas, panel interno).

## Datos biométricos: retención y borrado

- Imágenes de entrenamiento: carpeta privada por persona.
- Modelo LBPH: binario agregado, sin imágenes legibles.
- **Eliminar persona** = borrar carpeta de imágenes + `face_profile`.
  El modelo persiste hasta el próximo entrenamiento (así ninguna otra persona
  pierde su identidad y la etiqueta huérfana ya no puede conceder acceso).
- `access_events`: conservados como auditoría (persona desreferenciada).
- Backups: en ubicación privada, `chmod 600`; puede contener biometría →
  tratar con el mismo nivel de protección.

## Consentimiento (RGPD / normativa local, si aplica)

Documentar: propósito, almacenamiento, lista de perfiles, cómo pedir
eliminación completa. Sólo registrar el rostro de quien da consentimiento
explícito y firmado.

## Ejecución segura del servicio

```bash
# NO usar app.run(debug=True) en producción; `python -m device.cli serve`
# ya arranca con debug=False y bind 127.0.0.1.
```

El puerto 5000 no debe estar en tu router; acceso remoto solo por VPN
(docs/remote-access.md).
