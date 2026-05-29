# Deploy Guide — BTC Arbitrage Bot

Estado actual (2026-05-29):
| Componente | Estado | URL |
|---|---|---|
| Frontend (Vercel) | LIVE | https://frontend-plum-three-76.vercel.app |
| Backend (Cloud Run) | PENDIENTE — requiere auth gcloud | — |

---

## Paso 1 — Autenticar gcloud (solo una vez por máquina)

Corre estos comandos TÚ en la terminal (requieren navegador):

```bash
! gcloud auth login
! gcloud auth application-default login
```

Luego configura el proyecto:

```bash
! gcloud config set project <TU_PROJECT_ID>
! gcloud config set run/region us-central1
```

Para encontrar tu PROJECT_ID:
- Consola GCP → selector de proyecto (arriba izquierda) → copiar el ID
- O: `gcloud projects list`

Verifica que quedó bien:
```bash
! gcloud config list
```

Debes ver `project = <tu-project-id>` sin errores.

---

## Paso 2 — Habilitar APIs de GCP (si es proyecto nuevo)

```bash
! gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com
```

Tarda ~30 segundos. Solo se necesita una vez por proyecto.

---

## Paso 3 — Deploy del backend a Cloud Run

```bash
bash scripts/deploy-backend.sh
```

El script hace:
1. `gcloud run deploy arb-backend --source backend/` — buildea el Dockerfile y despliega
2. Imprime la URL del servicio al final

**Variables de entorno en Cloud Run** (se pasan via `--set-env-vars` en el script):
- `DB_PATH=/tmp/arb.db` — DuckDB en disco efímero del contenedor (se reinicia en cada deploy)
- Para persistencia real agregar Cloud Storage mount o Cloud SQL

Duración esperada: 3-5 minutos en el primer deploy, ~2 min en redeploys.

---

## Paso 4 — Apuntar el frontend al backend

Una vez que Cloud Run te dé la URL (ej. `https://arb-backend-xxxx-uc.a.run.app`):

```bash
NEXT_PUBLIC_API_URL=https://arb-backend-xxxx-uc.a.run.app \
  bash scripts/deploy-frontend.sh
```

El script actualiza la env var en Vercel y hace redeploy automático.

**Importante**: el frontend conecta el WebSocket a `ws://localhost:8000/ws/live`
hardcodeado en `frontend/hooks/useArbitrageData.ts`. Para producción hay que cambiarlo
a la URL de Cloud Run:

```bash
# frontend/hooks/useArbitrageData.ts, línea ~20
# Cambiar:
const WS_URL = 'ws://localhost:8000/ws/live'
# Por:
const WS_URL = (process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8000/ws/live')
```

Y agregar la variable a Vercel:
```bash
cd frontend
echo "wss://arb-backend-xxxx-uc.a.run.app/ws/live" | npx vercel env add NEXT_PUBLIC_WS_URL production
```

---

## Paso 5 — Verificar que todo funciona

```bash
# Backend health
curl https://arb-backend-xxxx-uc.a.run.app/health

# Trades (vacío hasta que haya actividad real o DEMO_MODE=true)
curl https://arb-backend-xxxx-uc.a.run.app/api/trades

# Circuit breaker
curl https://arb-backend-xxxx-uc.a.run.app/api/circuit-breaker
```

Para activar datos demo (trades sintéticos cada 10s):
```bash
gcloud run services update arb-backend \
  --update-env-vars DEMO_MODE=true \
  --region us-central1
```

Para forzar el circuit breaker en demo (muestra el safety mechanism):
```bash
curl -X POST https://arb-backend-xxxx-uc.a.run.app/api/circuit-breaker/open
# Vuelve a cerrarlo:
curl -X POST https://arb-backend-xxxx-uc.a.run.app/api/circuit-breaker/reset
```

---

## Redeploy rápido (cambios normales)

```bash
# Solo backend:
bash scripts/deploy-backend.sh

# Solo frontend:
bash scripts/deploy-frontend.sh

# Ambos en secuencia:
bash scripts/deploy-backend.sh && bash scripts/deploy-frontend.sh
```

---

## Troubleshooting

**Error: `The project property is set to the empty string`**
→ Correr Paso 1 completo. Verificar con `gcloud config get project`.

**Error: `PERMISSION_DENIED` al buildear**
→ La cuenta necesita roles: `Cloud Run Admin` + `Cloud Build Editor` + `Storage Admin`.
Pedir al dueño del proyecto que los asigne, o usar la cuenta de servicio del proyecto.

**Frontend conecta a localhost en producción**
→ La variable `NEXT_PUBLIC_WS_URL` no está seteada en Vercel. Ver Paso 4.

**Circuit breaker se abre solo**
→ Probablemente 3 trades `ABORTED_STALE` consecutivos (spreads desaparecen antes de ejecutar).
Normal en mercado tranquilo. Esperar 60s o hacer `POST /api/circuit-breaker/reset`.

**Logs del backend en tiempo real**:
```bash
gcloud run services logs tail arb-backend --region us-central1
```
