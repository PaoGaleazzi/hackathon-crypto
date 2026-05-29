# BTC Arbitrage Engine

Real-time Bitcoin cross-exchange arbitrage detection and execution system. Monitors BBO (Best Bid/Offer) across three exchanges via persistent WebSocket connections, computes net profitability including fees and slippage, and executes simulated trades through a prioritized opportunity queue — not FIFO.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         DATA LAYER  (asyncio tasks)                  │
│                                                                      │
│  Binance WS ──► BinanceAdapter ─┐                                   │
│  Kraken WS  ──► KrakenAdapter  ─┼──► Normalizer ──► BBO State       │
│  [+ adapters]                   ┘      (UTC ts)     (in-memory dict) │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ tick event (BBO updated)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         CORE  (hot path — no I/O)                    │
│                                                                      │
│  Scanner  ──► calculates P(q) for all N·(N-1)/2 exchange pairs      │
│     │         filters: net_profit > MIN_PROFIT_USD                   │
│     │                  quote_age  < STALE_QUOTE_MS                   │
│     ▼                                                                │
│  OpportunityScorer  ──► priority queue, composite score:             │
│     │                   net_spread_pct × liquidity                   │
│     │                   × freshness_decay(age_ms)                    │
│     │                   − volatility_penalty(σ_10s)                  │
│     ▼                                                                │
│  OptimalSizer  ──► q* = net_spread / (2λ)  [analytic, not greedy]   │
│     ▼                                                                │
│  ExecutionSimulator ──► pre-exec revalidation                        │
│     │                   circuit breaker check (volatility 10s)       │
│     │                   partial fill guard (MIN_FILL_RATIO)          │
│     └──► trade recorded  OR  REJECTED_NEGATIVE_NET                   │
│                           OR  ABORTED_STALE                          │
│                           OR  SKIPPED_MIN_FILL                       │
└──────────────────────────┬───────────────────────────────────────────┘
                           │ async write (never blocks hot path)
                           ▼
                      ┌─────────┐
                      │ DuckDB  │  opportunities, trades, latency stats
                      └────┬────┘
                           │
                    ┌──────┴──────┐
                    │  FastAPI    │  REST + /ws/live WebSocket push
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │  Next.js 15 │  TradingView charts, shadcn/ui
                    │  Dashboard  │  real-time BBO, P&L, circuit state
                    └─────────────┘
```

**Critical invariant**: DuckDB is never on the detection hot path. BBO state and scoring are 100% in-memory. DuckDB receives async writes after the execution decision.

---

## Evaluation Criteria

### C1 — Detection Latency

WebSocket-only feeds — no HTTP polling anywhere in the codebase. A single `asyncio` event loop handles all exchange connections without cross-task blocking.

Every tick carries a chained timestamp pipeline:
```
ws_received_at → normalized_at → scanned_at → scorer_ranked_at → executor_decided_at
```
Decision latency = `executor_decided_at − ws_received_at`. Persisted in DuckDB and served as `p50 / p95 / p99` at `/api/metrics/latency`. Quotes older than `STALE_QUOTE_MS` (default 500ms) are rejected before execution.

### C2 — Net Profitability Accuracy

Fee model uses verified taker rates from each exchange's official documentation (`FeeModel` in `core/fees.py`). Slippage is estimated dynamically from order book depth, not hardcoded:

```
λ = spread_at_depth / total_volume_available   (recalculated each tick)

P(q) = q·(bid_B − ask_A)
     − q·ask_A·fee_A
     − q·bid_B·fee_B
     − λ·q²
     − W_fixed
```

Optimal size `q*` is solved analytically (`dP/dq = 0` → `q* = net_spread / (2λ)`), then clipped to available liquidity and wallet balances. Opportunities with `P(q*) ≤ 0` are recorded as `REJECTED_NEGATIVE_NET` and never executed. Every trade record contains the full breakdown: `gross_spread`, `fee_buy`, `fee_sell`, `slippage_est`, `net_profit`.

### C3 — Robustness

Three independent protection mechanisms in `ExecutionSimulator`:

| Mechanism | Trigger | Outcome |
|---|---|---|
| Stale re-validation | Price moved since detection | `ABORTED_STALE` |
| Circuit breaker | `\|Δprice/price\| > 0.05%` in 10s window | All execution paused for 30s |
| Partial fill guard | Available liquidity < 30% of `q*` | `SKIPPED_MIN_FILL` (withdrawal cost not amortized) |

Wallet balances update atomically inside the single event loop — no race conditions by design. The circuit breaker state (`OPEN`/`CLOSED` + countdown) is exposed in `/api/status` and visible on the dashboard.

### C4 — Intelligence and Strategy

The scanner evaluates all `N·(N−1)/2` exchange pairs on every tick. With 3 exchanges that is 3 simultaneous pairs; adding a 4th gives 6 with no code changes.

`OpportunityScorer` sits between the scanner and the executor. It maintains a priority queue ordered by composite score:

```
score = net_spread_pct
      × min(ask_depth_A, bid_depth_B)
      × exp(−age_ms / 200)          ← freshness decay
      − execution_risk_penalty(σ_10s)
```

The executor always takes the highest-scoring opportunity, not the first detected. Two exchanges with equal spread but a 10× liquidity difference produce different scores.

`OptimalSizer` computes the position size that maximizes `P(q)` analytically rather than defaulting to "fill whatever is available" — a meaningful differentiator over greedy approaches.

### C5 — Code and Architecture Quality

Clean separation of concerns enforced at the module boundary:

```
backend/
  data/    WS adapters + BBO normalizer + in-memory state
  core/    scanner → scorer → sizer → executor (zero I/O)
  api/     FastAPI routes — thin wrappers only, no business logic
  models/  Pydantic models shared across layers
  db/      DuckDB connection singleton + schema DDL
tests/
  sanity/  one known-answer test per public numerical function
```

Every public Python function carries type hints. Pydantic models for all API request/response shapes. Functions stay under 50 lines; files under 300. Sanity tests cover `FeeModel`, `OptimalSizer`, `OpportunityScorer`, and profit calculations with hand-verified expected values.

### C6 — Deployed Web Interface

Live dashboard built with Next.js 15 App Router, shadcn/ui components, and TradingView Lightweight Charts for the P&L curve.

| Panel | Data source | Update frequency |
|---|---|---|
| BBO price feed | `/ws/live` push | ~100ms |
| Opportunity queue | `/ws/live` push | each tick |
| Trade log + breakdown | REST polling | 2s |
| P&L chart (TradingView) | REST polling | 2s |
| Latency (p50/p95) | `/ws/live` push | 1s |
| Circuit breaker state | `/ws/live` push | on change |
| Wallet balances | `/ws/live` push | after each trade |

Backend: [Cloud Run](https://cloud.google.com/run) — `arb-backend` service, `us-central1`.  
Frontend: [Vercel](https://vercel.com) — Next.js deploy.

---

## Running Locally

```bash
# 1. Environment
cp .env.example .env

# 2. Backend
cd backend && uv pip install -r requirements.txt && uvicorn api.main:app --reload --port 8000

# 3. Frontend
cd frontend && npm install && npm run dev
```

Backend API: `http://localhost:8000`  
Frontend: `http://localhost:3000`  
API docs: `http://localhost:8000/docs`

---

## Deploying to Cloud Run

```bash
bash scripts/deploy-backend.sh
```

Reads `GCP_PROJECT_ID` from the environment or from the active `gcloud` config. Prints the public service URL on completion. The script calls `gcloud run deploy --source backend/` — no Docker build step required locally; Cloud Build handles it.

For the frontend, connect the repository to Vercel and set `NEXT_PUBLIC_API_URL` to the Cloud Run service URL.

---

## Key Technical Decisions

### WebSockets over polling

HTTP polling at 1-second intervals introduces 0–1000ms of additional detection latency by construction. WebSocket streams deliver order book updates within tens of milliseconds of market events. At the spreads this system targets (fractions of a percent of BTC price), the difference between detecting an opportunity at 50ms vs 800ms is often the difference between capturing it and missing it.

### In-memory BBO state, DuckDB for persistence

Embedding any database on the hot path — even an embedded one — adds microseconds to milliseconds of latency per event and introduces GIL contention when run from an async context. BBO state is a plain Python dict keyed by `Exchange` enum. It is never queried during detection or scoring.

DuckDB is used exclusively for analytics and audit: persisting the full trade log, latency statistics, and opportunity history. Writes happen in `asyncio.to_thread()` tasks that never block the event loop. DuckDB's columnar storage and SQL interface make historical analysis and the trade breakdown queries efficient without running a separate database server.

### Analytic position sizing vs greedy

A greedy sizer takes `min(available_depth_A, available_depth_B)` as the trade size. This ignores slippage: as size increases, the marginal spread narrows and the slippage cost grows quadratically. The profit function `P(q) = q·net_spread − λ·q²` is strictly concave, with a unique maximum at `q* = net_spread / (2λ)`. The OptimalSizer computes this analytically rather than scanning over candidate sizes, then clips to balance and depth constraints.

### Single event loop, no threading on the hot path

Python's asyncio model guarantees that only one coroutine runs at a time within a loop, eliminating the need for locks on shared BBO state. This is not a limitation — it is the design. The scanner, scorer, sizer, and executor are all `async def` functions that yield only at explicit `await` points, which never appear in the numerical hot path.

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API framework | FastAPI 0.115 |
| Async runtime | asyncio (single event loop) |
| Market feeds | WebSocket (native `websockets` library) |
| Analytics DB | DuckDB 1.1 (embedded, async writes only) |
| Data models | Pydantic v2 |
| Frontend | Next.js 15 (App Router) |
| UI components | shadcn/ui + Tailwind CSS |
| Financial charts | TradingView Lightweight Charts |
| Backend deploy | Google Cloud Run |
| Frontend deploy | Vercel |
| Containerization | Docker (multi-stage, slim base) |
| CI/CD | GitHub Actions → Cloud Run |
