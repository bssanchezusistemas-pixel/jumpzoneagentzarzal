# Supabase — Jumping Fit

Migraciones en `migrations/` (ejecutar en orden):

| Archivo | Contenido |
|---------|-----------|
| `001_jumping_schema.sql` | class_types, slots, clients, bookings |
| `002_planes_produccion.sql` | plans, packages, payment_receipts |
| `003_bot_meta.sql` | mensajes (memoria IA), wa_sessions |

## Crear proyecto

- Región recomendada: **sa-east-1** (São Paulo)
- Nombre sugerido: `jumping-fit`

## Aplicar

```bash
# Con psql (connection string directa puerto 5432)
export SUPABASE_DB_URL='postgresql://postgres.[ref]:[pass]@db.[ref].supabase.co:5432/postgres'
./scripts/apply_supabase_migrations.sh
```

## DATABASE_URL app (Railway)

Pooler transaction mode, puerto **6543**:

```
postgresql+asyncpg://postgres.[ref]:[pass]@aws-0-sa-east-1.pooler.supabase.com:6543/postgres
```

Ver runbook completo: [`docs/PRODUCCION_CLOUDFLARE_SUPABASE.md`](../docs/PRODUCCION_CLOUDFLARE_SUPABASE.md).
