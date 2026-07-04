# Cloudflare — Jumping Fit API

Pasos detallados en [`docs/PRODUCCION_CLOUDFLARE_SUPABASE.md`](PRODUCCION_CLOUDFLARE_SUPABASE.md#fase-4--cloudflare).

## Resumen

1. Railway → Custom Domain → `api.tudominio.com`
2. Cloudflare DNS → CNAME `api` → `[proyecto].up.railway.app` (proxy ON)
3. SSL/TLS → **Full (strict)**
4. Probar: `curl https://api.tudominio.com/health`

## URLs para Meta webhook

- Callback: `https://api.tudominio.com/webhook`
- Verify token: valor de `META_VERIFY_TOKEN` en Railway
