# Jumping Fit — Producción: Cloudflare + Supabase + Meta coexistence

Runbook para desplegar el bot JumpBot en producción con Meta Cloud API directa (coexistence vía tech provider Chile).

## Arquitectura

```
Meta webhook → Cloudflare (DNS/SSL) → Railway (Docker FastAPI) → Supabase Postgres
```

| Capa | Servicio | Rol |
|------|----------|-----|
| WhatsApp | Meta Cloud API | Mensajes entrantes/salientes |
| Compute | Railway | FastAPI + web `/web/` + recordatorios |
| DNS/SSL | Cloudflare | `api.tudominio.com` → Railway |
| BD | Supabase sa-east-1 | Reservas, planes, memoria bot |

**Importante:** mantener **1 réplica** en Railway (APScheduler recordatorios).

---

## Fase 1 — Supabase

### 1.1 Crear proyecto

1. [supabase.com/dashboard](https://supabase.com/dashboard) → New project
2. Nombre: `jumping-fit`
3. Región: **South America (São Paulo)** `sa-east-1`
4. Guardar contraseña de `postgres`

> Si aparece *"maximum limits for free projects"*: pausa otro proyecto inactivo o upgrade el plan antes de crear uno nuevo.

### 1.2 Aplicar migraciones

En **SQL Editor**, ejecutar en orden:

1. [`supabase/migrations/001_jumping_schema.sql`](../supabase/migrations/001_jumping_schema.sql)
2. [`supabase/migrations/002_planes_produccion.sql`](../supabase/migrations/002_planes_produccion.sql)
3. [`supabase/migrations/003_bot_meta.sql`](../supabase/migrations/003_bot_meta.sql)

O con `psql`:

```bash
export SUPABASE_DB_URL='postgresql://postgres.[ref]:[PASSWORD]@db.[ref].supabase.co:5432/postgres'
./scripts/apply_supabase_migrations.sh
```

### 1.3 DATABASE_URL para Railway

En Supabase → **Settings → Database → Connection string**:

- Modo: **Transaction**
- Pooler, puerto **6543**
- Formato para la app:

```env
DATABASE_URL=postgresql+asyncpg://postgres.[ref]:[PASSWORD]@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
```

La app convierte `postgresql://` → `postgresql+asyncpg://` automáticamente en [`agent/memory.py`](../agent/memory.py).

### 1.4 Storage (opcional, fase 1b)

Bucket privado `comprobantes` para imágenes de pago (hoy se guarda referencia `meta:media_id`).

---

## Fase 2 — Meta Cloud API (código)

Proveedor implementado en [`agent/providers/meta.py`](../agent/providers/meta.py):

| Feature | Detalle |
|---------|---------|
| GET `/webhook` | Verificación `hub.verify_token` + `hub.challenge` |
| POST `/webhook` | Parseo `messages[]`, firma `X-Hub-Signature-256` |
| Imagen / audio | Descarga vía Graph API + transcripción |
| Coexistence | Ignora `smb_message_echoes` / `message_echoes` (`es_propio=True`) |
| Envío | POST `graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages` |

Variables Railway:

```env
WHATSAPP_PROVIDER=meta
META_ACCESS_TOKEN=
META_PHONE_NUMBER_ID=
META_VERIFY_TOKEN=jumping-fit-verify-2026
META_APP_SECRET=
META_WABA_ID=
ENVIRONMENT=production
WEB_PUBLIC_URL=https://api.tudominio.com/web/
```

---

## Fase 3 — Railway

1. [railway.app](https://railway.app) → New Project → **Deploy from GitHub** → repo `whatsapp-agentkit`
2. Railway detecta [`Dockerfile`](../Dockerfile) y [`railway.json`](../railway.json)
3. **Settings → Variables** — copiar desde [`.env.example`](../.env.example):

| Variable | Obligatoria |
|----------|-------------|
| `DATABASE_URL` | Sí |
| `WHATSAPP_PROVIDER=meta` | Sí |
| `META_*` | Sí (post handoff TP) |
| `OPENROUTER_API_KEY` o `ANTHROPIC_API_KEY` | Sí |
| `SECRET_KEY` | Sí |
| `ADMIN_USER` / `ADMIN_PASSWORD` | Sí |
| `WEB_PUBLIC_URL` | Sí |
| `ENVIRONMENT=production` | Sí |
| `PORT` | Railway lo inyecta |

4. Verificar deploy: `https://[proyecto].up.railway.app/health` → `{"status":"ok",...}`

**No escalar** a más de 1 réplica.

---

## Fase 4 — Cloudflare

Asumiendo dominio `jumpingfit.co` (ajustar al real):

1. Cloudflare → DNS del dominio
2. Railway → **Settings → Networking → Custom Domain** → `api.jumpingfit.co`
3. Cloudflare: CNAME `api` → target que indica Railway (proxy **naranja** ON)
4. SSL/TLS → **Full (strict)**

URLs finales:

| Uso | URL |
|-----|-----|
| Webhook Meta | `https://api.tudominio.com/webhook` |
| Web reservas | `https://api.tudominio.com/web/` |
| Panel admin | `https://api.tudominio.com/admin` |
| Health | `https://api.tudominio.com/health` |

Actualizar [`config/business.yaml`](../config/business.yaml) → `web.url_publica`.

---

## Fase 5 — Handoff tech provider (Chile)

Enviar **antes** del día de corte:

### Mensaje al TP

```
Hola, para Jumping Fit (Colombia +57) necesitamos:

1. Onboarding Meta Cloud API con COEXISTENCE
   (número ya en WhatsApp Business — la dueña sigue en el celular)

2. Portfolio Meta: "power jump"

3. Al finalizar, entregar:
   - PHONE_NUMBER_ID
   - Access token permanente (System User)
   - WABA_ID
   - Confirmación coexistence activa (is_on_biz_app)

4. Webhook (lo configuramos nosotros):
   - Callback URL: https://api.tudominio.com/webhook
   - Verify token: jumping-fit-verify-2026
   - Campos suscritos: messages, smb_message_echoes

5. ¿Ustedes configuran el webhook o solo entregan credenciales?
```

### Checklist día D

| # | Responsable | Acción |
|---|-------------|--------|
| 1 | Dueña | WhatsApp **Business** en +57; portfolio **power jump** con admin |
| 2 | TP Chile | Embedded Signup **coexistence** (`Connect existing WhatsApp Business app`) |
| 3 | TP | Entregar `PHONE_NUMBER_ID`, token, `WABA_ID` |
| 4 | Dev | Meta Developers → Webhook → URL producción + verify token |
| 5 | Dev | Railway variables `META_*`, redeploy |
| 6 | Dev | Cliente escribe al +57 → bot responde |
| 7 | Dueña | Confirma que sigue viendo chats en el celular |
| 8 | Dev | Dueña responde desde celular → bot **no** duplica (ecos ignorados) |

### Configurar webhook en Meta (si lo haces tú)

1. [developers.facebook.com](https://developers.facebook.com) → App → WhatsApp → Configuration
2. Callback URL: `https://api.tudominio.com/webhook`
3. Verify token: mismo que `META_VERIFY_TOKEN` en Railway
4. Suscribir: `messages`, `smb_message_echoes`
5. Al guardar, Meta hace GET de verificación — debe devolver el `hub.challenge`

---

## Fase 6 — Cutover y pruebas E2E

### Smoke test automatizado

```bash
PROD_URL=https://api.tudominio.com \
META_VERIFY_TOKEN=jumping-fit-verify-2026 \
ADMIN_USER=admin \
ADMIN_PASSWORD=tu-password \
python scripts/prod_smoke_test.py
```

### Pruebas manuales

1. **Health** — `/health` responde OK
2. **Web** — reserva plan semana → aparece en Supabase `client_packages`
3. **Admin** — login `/admin` → confirmar pago pendiente
4. **WhatsApp** — mensaje al +57 → JumpBot responde con link web producción
5. **Comprobante** — enviar imagen → registro en `payment_receipts`
6. **Coexistence** — dueña responde desde celular; bot no contesta el eco

### Dev local vs producción

| Entorno | WhatsApp | BD |
|---------|----------|-----|
| Local | Twilio sandbox | SQLite |
| Producción | Meta Cloud API | Supabase |

---

## Migrar de Railway a otro host (~30 min)

1. Mismo Docker en Fly/VPS/Render
2. Copiar variables de entorno
3. Cloudflare: cambiar CNAME `api` al nuevo host
4. Meta: actualizar webhook URL (misma ruta `/webhook`)

---

## Troubleshooting

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| Webhook no verifica | `META_VERIFY_TOKEN` distinto en Meta vs Railway | Unificar valor |
| 403 en POST webhook | `META_APP_SECRET` incorrecto | Copiar App Secret de Meta Developers |
| Bot no responde | Token expirado o `PHONE_NUMBER_ID` wrong | Regenerar con TP |
| Bot duplica respuestas | Ecos coexistence procesados | Verificar `es_propio` en logs |
| Recordatorios duplicados | Más de 1 réplica Railway | Escalar a 1 |
| BD error al arrancar | Migraciones no aplicadas | Ejecutar 001–003 |

---

## Referencias

- [Meta coexistence onboarding](https://developers.facebook.com/docs/whatsapp/embedded-signup/custom-flows/onboarding-business-app-users)
- [Meta webhook reference](https://developers.facebook.com/docs/graph-api/webhooks/getting-started)
- Instagram Jumping Fit: https://www.instagram.com/jumping__fit_/
