#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/deploy-frontend.sh                          # deploy con vars actuales
#   NEXT_PUBLIC_API_URL=https://your-url bash scripts/...   # sobreescribir URL del backend

FRONTEND_DIR="$(cd "$(dirname "$0")/../frontend" && pwd)"

echo "Building and deploying frontend to Vercel..."
echo "Dir: $FRONTEND_DIR"

cd "$FRONTEND_DIR"

# Si se pasa la URL del backend, actualizarla en Vercel env antes del deploy
if [[ -n "${NEXT_PUBLIC_API_URL:-}" ]]; then
  echo "Setting NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL"
  # Elimina si ya existe, agrega nueva (Vercel falla si ya existe sin --force)
  npx vercel env rm NEXT_PUBLIC_API_URL production --yes 2>/dev/null || true
  echo "$NEXT_PUBLIC_API_URL" | npx vercel env add NEXT_PUBLIC_API_URL production
fi

npx vercel --prod --yes

echo ""
echo "Frontend deployed."
