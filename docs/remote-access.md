# Acceso remoto seguro (NO exponer el 5000 a Internet)

## Reglas

- El Flask de la Pi **queda solo en la red local** (`FLASK_HOST=127.0.0.1`
  o LAN privada). Jamás abrir el 5000 en el router.
- El panel web puede publicarse en Vercel, pero hablará con la Pi por un
  **canal privado autenticado** (VPN o túnel): nunca con la IP pública directa.
- Recomendado: **Tailscale/ZeroTier** (WireGuard) en la Pi y en los equipos
  de administración.

## Setup con Tailscale (sencillo y seguro)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip   # ej.: 100.x.y.z  (solo la red privada)
```

- En los equipos de administración: instalar Tailscale e iniciar sesión.
- El panel web (Vercel) accede a `http://100.x.y.z:5000`
  OJO: un navegador NO puede usar 100.x.y.z desde Vercel: la clave es que la
  sesión del Navegador admin esté en la red VPN. Para usar el panel en Vercel
  sin VPN, instala un proxy autenticado (Cloudflare Access / túnel propio):

```text
Navegador (internet) → Vercel (static) → Cloudflare Access → túnel HTTPS → Pi
```

Los túneles (cloudflared, ngrok con restricciones) cuentan como canal
privado autenticado: los clientes deben autenticarse antes de llegar a la Pi.

## HTTPS

El propio Flask **no** sirve producción TLS. Si accedes directo en LAN y
quieres https, pon Nginx + `certbot` en la Pi:

```nginx
server {
  listen 443 ssl;
  server_name pi.tu-dominio.local;
  ssl_certificate     /etc/letsencrypt/live/pi/...;
  ssl_certificate_key /etc/letsencrypt/live/pi/...;
  location /api/ { proxy_pass http://127.0.0.1:5000; }
}
```

## Supabase (sincronización)

- Solo la Pi tiene `SUPABASE_SERVICE_ROLE_KEY`; el frontend **no** la recibe.
- Las tablas tienen RLS (migrations/0002): un usuario anónimo no lee nada.
- Primero crea el usuario de administración en Supabase Auth y entonces
  ejecuta en el SQL editor de Supabase:

```sql
select bootstrap_first_admin('<uuid-del-usuario>'::uuid);
```

- Conexión con Supabase sobre HTTPS automáticamente.

## Comprobación final de exposición

```bash
# desde FUERA de tu red, comprueba que no se vea nada de la Pi:
# nmap -p 5000 192.168.1.11   → filtered/closed
# https://www.grc.com/shieldsup → responder: invisible
# además: el puerto del panel web (5173/443) solo desde la VPN.
```
