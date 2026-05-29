# Deploy Notes

## Estado actual

| Componente | Estado | URL |
|------------|--------|-----|
| Frontend (Vercel) | ✅ LIVE | https://frontend-plum-three-76.vercel.app |
| Backend (Cloud Run) | ❌ Pendiente — gcloud sin auth | — |

---

## Frontend — Vercel (COMPLETO)

Deployado el 2026-05-29 a producción. Proyecto linkeado como
`paomichelle2001-4543s-projects/frontend`.

URL canónica: **https://frontend-plum-three-76.vercel.app**
Inspect: https://vercel.com/paomichelle2001-4543s-projects/frontend/F9Jm2TwDXws7jp1tPvYkr3vb42Zw

Para redeploys futuros desde la raíz del repo:
```bash
cd frontend && npx vercel --prod --yes
```

**Pendiente**: una vez que el backend esté en Cloud Run, agregar la variable de entorno:
```bash
cd frontend
npx vercel env add NEXT_PUBLIC_API_URL production
# ingresar: https://<cloud-run-url>
npx vercel --prod --yes   # redeploy para que tome la variable
```

---

## Backend — Cloud Run (PENDIENTE: requiere acción manual)

### Error actual
```
ERROR: (gcloud.run.deploy) The project property is set to the empty string.
```
`gcloud` no tiene cuenta autenticada ni proyecto configurado en este entorno.

### Pasos para Pao (en orden)

**1. Autenticar gcloud** (abre browser):
```bash
gcloud auth login
```

**2. Configurar el proyecto GCP**:
```bash
gcloud config set project TU_PROJECT_ID
# Si no tienes proyecto: gcloud projects create arb-bot-hackathon --name="Arb Bot"
# Habilitar Cloud Run y Cloud Build:
gcloud services enable run.googleapis.com cloudbuild.googleapis.com
```

**3. Correr el deploy script**:
```bash
bash scripts/deploy-backend.sh
# O equivalente directo:
gcloud run deploy arb-backend \
  --source backend/ \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars DB_PATH=/tmp/arb.db \
  --port 8080
```

El script imprime la URL del servicio al final. Tarda ~3-5 min la primera vez (Cloud Build).

**4. Conectar frontend con el backend**:
```bash
cd frontend
npx vercel env add NEXT_PUBLIC_API_URL production
# pegar la URL de Cloud Run: https://arb-backend-xxxx-uc.a.run.app
npx vercel --prod --yes
```

### Notas importantes para Cloud Run

- `DB_PATH=/tmp/arb.db` — DuckDB en `/tmp`, que es efímero. Los datos se pierden al reiniciar el contenedor. Aceptable para hackathon; en producción usaría Cloud Storage o Firestore.
- Cloud Run escala a cero cuando no hay tráfico. Los WS adapters (Binance/Kraken/OKX) se desconectan. Configurar **min-instances=1** para que el bot corra 24/7:
  ```bash
  gcloud run services update arb-backend \
    --min-instances=1 \
    --region=us-central1
  ```
- El `Dockerfile` ya tiene `exec` para que SIGTERM de Cloud Run llegue a uvicorn directamente.

---

## Variables de entorno de producción

Todas con valores default seguros en `config.py`. Nada sensible expuesto.

```bash
DB_PATH=/tmp/arb.db
MIN_PROFIT_USD=1.0
MIN_FILL_RATIO=0.3
STALE_QUOTE_MS=500
CIRCUIT_BREAKER_THRESHOLD=0.0005
CIRCUIT_BREAKER_COOLDOWN_S=30
```

No hay API keys requeridas — todos los feeds WS (Binance, Kraken, OKX) son públicos.

---

## Checklist pre-demo

- [ ] `bash scripts/deploy-backend.sh` exitoso, URL impresa
- [ ] `curl https://<cloud-run-url>/health` devuelve `{"status":"ok"}`
- [ ] `curl https://<cloud-run-url>/api/status` muestra `"exchanges_connected":["binance","kraken","okx"]`
- [ ] `NEXT_PUBLIC_API_URL` seteada en Vercel con la URL de Cloud Run
- [ ] Frontend redesplegado, dashboard carga datos en vivo
- [ ] `gcloud run services update arb-backend --min-instances=1` — bot corre 24/7
