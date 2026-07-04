#!/usr/bin/env bash
# Aplica migraciones Jumping Fit en Supabase (SQL Editor o psql)
# Uso: SUPABASE_DB_URL='postgresql://...' ./scripts/apply_supabase_migrations.sh

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MIGRATIONS=(
  "$ROOT/supabase/migrations/001_jumping_schema.sql"
  "$ROOT/supabase/migrations/002_planes_produccion.sql"
  "$ROOT/supabase/migrations/003_bot_meta.sql"
)

if [[ -z "${SUPABASE_DB_URL:-}" ]]; then
  echo "Define SUPABASE_DB_URL (connection string directa puerto 5432, no pooler)."
  echo "Ejemplo: postgresql://postgres.[ref]:[pass]@db.[ref].supabase.co:5432/postgres"
  exit 1
fi

for f in "${MIGRATIONS[@]}"; do
  echo "==> $(basename "$f")"
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$f"
done

echo "Migraciones aplicadas."
