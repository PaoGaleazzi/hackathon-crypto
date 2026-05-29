# BTC Arbitrage Bot

## Stack
- Backend: Python 3.12 + FastAPI + DuckDB + asyncio WebSockets
- Frontend: Next.js 15 + shadcn/ui + TradingView Lightweight Charts
- Deploy: GCP Cloud Run (backend), Vercel (frontend)

## Key design decisions
- DuckDB is NOT in the detection hot path. BBO state and scoring are 100% in-memory.
- Single asyncio event loop for all WS connections. No threading on the hot path.
- All timestamps UTC. BBO state keyed by Exchange enum.
- Opportunity execution goes through a priority queue (OpportunityScorer), never FIFO.

## Running locally
```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

## Running tests
```bash
cd backend
pytest -x --tb=short
```

## Deploy to Cloud Run
```bash
gcloud run deploy arb-backend \
  --source ./backend \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8080
```

## Module map
```
backend/
  data/       WS adapters + BBO normalizer + in-memory state
  core/       scanner → scorer → sizer → executor (hot path)
  api/        FastAPI routes (thin wrappers only)
  models/     Pydantic/dataclass models shared across layers
  db/         DuckDB connection singleton + schema DDL
```

## Reference
- docs/rubrica.md  — evaluation criteria + phase checklist
- docs/reto.md     — full problem statement
