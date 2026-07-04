# Cutover producción — Jumping Fit

Checklist día D (Meta coexistence + Railway + Supabase).

## Pre-requisitos

- [ ] Proyecto Supabase `jumping-fit` (sa-east-1) con migraciones 001–003 aplicadas
- [ ] Railway deploy OK — `/health` responde
- [ ] Cloudflare CNAME `api.tudominio.com` → Railway, SSL Full (strict)
- [ ] `WEB_PUBLIC_URL` y `config/business.yaml` → `url_publica` actualizados
- [ ] Credenciales Meta del tech provider Chile recibidas

## Cutover (orden)

1. [ ] TP: Embedded Signup coexistence sobre +57 (dueña confirma en celular)
2. [ ] Railway: set `WHATSAPP_PROVIDER=meta` + `META_*` + redeploy
3. [ ] Meta Developers: webhook → `https://api.tudominio.com/webhook`, verify token, campos `messages` + `smb_message_echoes`
4. [ ] Smoke test:
   ```bash
   PROD_URL=https://api.tudominio.com \
   WHATSAPP_PROVIDER=meta \
   META_VERIFY_TOKEN=jumping-fit-verify-2026 \
   ADMIN_USER=admin \
   ADMIN_PASSWORD=*** \
   python scripts/prod_smoke_test.py
   ```
5. [ ] WhatsApp: cliente escribe al +57 → JumpBot responde
6. [ ] Web: reserva completa → fila en Supabase
7. [ ] Admin: login → confirmar pago → cliente recibe WhatsApp Meta
8. [ ] Coexistence: dueña responde desde celular → **bot no** responde al eco

## Rollback

- Cambiar webhook Meta a URL anterior (o desactivar)
- Railway: `WHATSAPP_PROVIDER=twilio` solo si sandbox sigue activo (dev)
- Dueña sigue usando WhatsApp Business app sin cambios

Ver runbook completo: [`PRODUCCION_CLOUDFLARE_SUPABASE.md`](PRODUCCION_CLOUDFLARE_SUPABASE.md)
