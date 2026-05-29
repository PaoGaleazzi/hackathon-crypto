# BTC Arbitrage Engine

Real-time Bitcoin cross-exchange arbitrage detection and execution system. Monitors BBO (Best Bid/Offer) across **7 exchanges** via persistent WebSocket connections, computes net profitability including fees and slippage, and executes simulated trades through a prioritized, analytically-sized opportunity queue.

Three concurrent strategies run in the same asyncio loop: **spatial arbitrage** (direct cross-exchange spread), **statistical arbitrage** (OU mean-reversion), and **triangular arbitrage** (Bellman-Ford negative-cycle detection treating USD and USDT as distinct nodes). A mean-variance QP allocator distributes capital across simultaneous opportunities.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     DATA LAYER  (7 asyncio tasks)                        │
│                                                                          │
│  Binance  ──►─┐                                                          │
│  Kraken   ──►─┤                                                          │
│  Coinbase ──►─┤                                                          │
│  OKX      ──►─┼──► Normalizer ──► BBO State   (in-memory dict)          │
│  Bybit    ──►─┤     (UTC ts)      keyed by Exchange enum                 │
│  Gemini   ──►─┤                                                          │
│  Bitstamp ──►─┘                                                          │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ tick event (BBO updated)
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                 CORE  (hot path — zero I/O, zero locks)                  │
│                                                                          │
│  Scanner  ──► all N·(N-1)/2 pairs evaluated per tick (21 with 7 exch.)  │
│     │         filter: net_profit > MIN_PROFIT_USD, age < STALE_QUOTE_MS  │
│     │                                                                    │
│  StatArbDetector  ──► OU spread history per pair, z-score, half-life     │
│     │                 signals: LONG_A_SHORT_B | LONG_B_SHORT_A | NEUTRAL │
│     │                                                                    │
│  TriangularScanner ──► Bellman-Ford on log-rate graph                    │
│     │                  edges: BTC/USD, BTC/USDT, USD/USDT per exchange   │
│     │                  USD ≠ USDT (distinct nodes); real 3-leg cycles    │
│     │                                                                    │
│  OpportunityScorer ──► priority queue, composite score:                  │
│     │                  net_spread_pct × liquidity                        │
│     │                  × exp(−age_ms / 200)   ← freshness decay          │
│     │                  − volatility_penalty(σ_10s)                       │
│     │                                                                    │
│  OptimalSizer  ──► q* = net_spread / (2λ)  [analytic, concave P(q)]     │
│     │                                                                    │
│  PortfolioAllocator ──► mean-variance QP across simultaneous opps        │
│     │                   maximize: r^T·x − λ·x^T·Σ·x                     │
│     │                   subject to: 0 ≤ x ≤ wallet_caps                 │
│     │                                                                    │
│  ExecutionSimulator ──► pre-exec revalidation                            │
│     │                   Almgren-Chriss latency buffer                    │
│     │                   circuit breaker check (σ_10s window)             │
│     │                   partial fill guard (MIN_FILL_RATIO)              │
│     └──► EXECUTED | REJECTED_NEGATIVE_NET | ABORTED_STALE                │
│                    | SKIPPED_MIN_FILL | CIRCUIT_BREAKER_OPEN              │
└──────────────────────────────┬───────────────────────────────────────────┘
                               │ asyncio.to_thread() — never blocks hot path
                               ▼
                       ┌──────────────┐
                       │   DuckDB     │  trades, opportunities, latency stats
                       └──────┬───────┘
                              │
                     ┌────────┴────────┐
                     │   FastAPI       │  REST + /ws/live WebSocket push
                     └────────┬────────┘
                              │
                     ┌────────┴────────┐
                     │  Next.js 15     │  TradingView charts, shadcn/ui
                     │  Dashboard      │  BBO prices, P&L, z-score, CB state
                     └─────────────────┘
```

**Critical invariant**: DuckDB is never on the detection hot path. BBO state and scoring are 100% in-memory. DuckDB receives async writes after the execution decision.

---

## Mathematical Foundations

### Statistical Arbitrage — Ornstein-Uhlenbeck z-score

The spread between two exchange mid-prices follows an OU process:

```
s_t = mid_A(t) − mid_B(t)

z_t = (s_t − μ_s) / σ_s

dS_t = κ(μ − S_t)dt + σ dW_t
```

`μ_s` and `σ_s` are rolling statistics over a configurable window. The mean-reversion half-life is estimated via AR(1) regression:

```
Δs_t = α + β·s_{t-1} + ε_t
half_life = −log(2) / log(1 + β)
```

A signal fires when `|z_t| > ENTRY_ZSCORE`. The OU regime is validated by requiring `half_life < MAX_HALF_LIFE_S`.

### E[profit] with Freshness Decay

The opportunity scorer computes a time-adjusted expected profit:

```
score = net_spread_pct
      × min(depth_ask_A, depth_bid_B)
      × exp(−age_ms / τ)          τ = 200ms decay constant
      − k_vol · σ_10s             execution-risk penalty
```

Quotes older than `STALE_QUOTE_MS` (500ms) are hard-rejected before scoring.

### Latency Risk Buffer (Almgren-Chriss)

Execution is gated by an adverse-selection buffer derived from the Almgren-Chriss framework:

```
buffer(q) = k · σ_spread · √(Δt) · q

k = 1.6449          (z_{0.95}, one-sided 95th percentile)
σ_spread            rolling std of mid_A − mid_B (per-pair, 10s window)
Δt = latency_ms / 1000
```

A trade proceeds only when `net_spread > fees + slippage_est + buffer(q*)`. This rejects opportunities that appear profitable on a zero-latency quote but become negative under realistic execution delay.

### Optimal Position Sizing

Profit as a function of size is strictly concave:

```
P(q) = q · net_spread − λ_mkt · q²

dP/dq = net_spread − 2λ_mkt · q = 0

q* = net_spread / (2λ_mkt)
```

`λ_mkt` (market impact coefficient) is estimated from order-book depth: `λ_mkt = spread_at_depth / total_volume_available`, recalculated each tick. `q*` is clipped to `min(ask_depth_A, bid_depth_B, wallet_balance)`.

### Portfolio Allocation — Mean-Variance QP

When multiple opportunities are live simultaneously, capital is allocated via quadratic programming:

```
maximize   r^T · x  −  λ · x^T · Σ · x

subject to   0 ≤ x_i ≤ wallet_cap_i   ∀i
```

`r_i` = expected net return per unit capital for opportunity `i`.  
`Σ` = covariance matrix of per-unit returns (estimated from recent spread history).  
`λ` = risk-aversion parameter (default 1.0). At `λ=0` the problem collapses to greedy LP allocation.

Solved with CVXPY (OSQP backend). The allocation plan is broadcast as advisory — it informs sizing but does not replace the per-trade `q*` computation.

### Triangular Arbitrage — Bellman-Ford on Log-Rates

Each exchange contributes directed edges to a currency graph. Buy BTC at exchange X: `USDT → BTC` with rate `1/ask`. Sell BTC: `BTC → USD` with rate `bid`.

Edge weights are negated log-rates:

```
w(A → B) = −log(rate(A→B))
```

A negative-weight cycle in this graph corresponds to a profitable arbitrage. Bellman-Ford detects negative cycles in O(V·E). USD and USDT are **distinct nodes** — `Binance(USDT) → BTC → Kraken(USD) → Bitstamp(USDT)` is a real 3-currency triangle, not a tautology. A small conversion spread is charged for the USD↔USDT leg.

---

## Evaluation Criteria

### C1 — Detection Latency

WebSocket-only feeds — no HTTP polling anywhere in the codebase. A single `asyncio` event loop handles all 7 exchange connections without cross-task blocking. `uvloop` replaces the default event loop for ~2× throughput on I/O-bound coroutines. `orjson` replaces `json` for order-book parsing (~3× faster). `gc.freeze()` is called at startup to eliminate GC pauses on the hot path.

Measured p50 end-to-end decision latency: **< 5ms**.

Every tick carries a chained timestamp pipeline:
```
ws_received_at → normalized_at → scanned_at → scorer_ranked_at → executor_decided_at
```
Decision latency = `executor_decided_at − ws_received_at`. Persisted in DuckDB and served as `p50 / p95 / p99` at `/api/metrics/latency`.

### C2 — Net Profitability Accuracy

Fee model uses verified taker rates per exchange (`core/fees.py`). Slippage estimated dynamically from order-book depth per tick. Every trade record contains the full cost breakdown: `gross_spread`, `fee_buy`, `fee_sell`, `slippage_est`, `net_profit`.

Opportunities with `P(q*) ≤ 0` are recorded as `REJECTED_NEGATIVE_NET` and never executed. The dashboard's **Gross vs Net** panel shows the rejection funnel in real time.

### C3 — Robustness

Four independent protection mechanisms:

| Mechanism | Trigger | Outcome |
|---|---|---|
| Stale re-validation | Price moved since detection | `ABORTED_STALE` |
| Almgren-Chriss buffer | `net_spread < fees + k·σ·√Δt·q` | trade rejected |
| Circuit breaker | `\|Δprice/price\| > 0.05%` in 10s window | all execution paused 30s |
| Partial fill guard | Available depth < 30% of `q*` | `SKIPPED_MIN_FILL` |

Wallet balances update atomically inside the single event loop — no race conditions by design.

### C4 — Intelligence and Strategy

Three simultaneous, independent strategies:

1. **Spatial arbitrage** — direct cross-exchange BTC spread across all 21 pairs (7 exchanges). Scanner runs on every BBO tick.
2. **Statistical arbitrage** — OU-based z-score on per-pair spread history. Signals fire when `|z| > ENTRY_ZSCORE` with validated half-life.
3. **Triangular arbitrage** — Bellman-Ford on the log-rate currency graph. Detects USDT→BTC→USD→USDT cycles that exploit the USD/USDT basis.

The portfolio allocator runs mean-variance QP when multiple opportunities are live, ensuring capital is not over-concentrated in correlated pairs.

### C5 — Code and Architecture Quality

Clean separation of concerns enforced at the module boundary:

```
backend/
  data/       WS adapters (7 exchanges) + BBO normalizer + in-memory state
  core/       scanner → stat_arb → triangular → scorer → sizer
              → allocator → executor (zero I/O on hot path)
  api/        FastAPI routes — thin wrappers only, no business logic
  models/     Pydantic models shared across layers
  db/         DuckDB connection singleton + schema DDL
tests/
  sanity/     one known-answer test per public numerical function
```

180 tests. Every public Python function carries type hints. Sanity tests cover `FeeModel`, `OptimalSizer`, `OpportunityScorer`, `StatArbDetector`, `TriangularScanner`, `PortfolioAllocator`, and `LatencyRiskBuffer` with hand-verified expected values.

### C6 — Deployed Web Interface

Live dashboard built with Next.js 15 App Router, shadcn/ui components, and TradingView Lightweight Charts.

| Panel | Data source | Update frequency |
|---|---|---|
| BBO price feed | `/ws/live` push | ~100ms |
| Opportunity queue + Gross/Net funnel | `/ws/live` push | each tick |
| Z-score + OU signal | `/ws/live` push | each tick |
| Triangular arbitrage | REST polling | 2s |
| Trade log + cost breakdown | REST polling | 2s |
| P&L chart (TradingView) | REST polling | 2s |
| Latency waterfall (p50/p95/p99) | `/ws/live` push | 1s |
| Circuit breaker state + countdown | `/ws/live` push | on change |
| Wallet rebalance status | derived from trades | 2s |
| Presentation mode (key P) | client-side toggle | instant |

---

## How to Run

```bash
# Start everything (backend + frontend)
bash scripts/start-demo.sh

# Backend only
cd backend && uv pip install -r requirements.txt && uvicorn api.main:app --reload --port 8000

# Frontend only
cd frontend && npm install && npm run dev
```

Backend API: `http://localhost:8000`  
Frontend: `http://localhost:3000`  
API docs: `http://localhost:8000/docs`  
WebSocket: `ws://localhost:8000/ws/live`

For deployment to Cloud Run + Vercel:

```bash
bash scripts/deploy-backend.sh   # GCP Cloud Run (us-central1)
bash scripts/deploy-frontend.sh  # Vercel
```

---

## Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| API framework | FastAPI 0.115 |
| Async runtime | asyncio + uvloop 0.21 (2× faster event loop) |
| JSON parsing | orjson (3× faster than stdlib json) |
| Market feeds | WebSocket (native `websockets` library), 7 exchanges |
| Analytics DB | DuckDB 1.1 (embedded, async writes only) |
| Data models | Pydantic v2 |
| Optimization | CVXPY + OSQP (mean-variance QP) |
| Frontend | Next.js 15 (App Router) |
| UI components | shadcn/ui + Tailwind CSS |
| Financial charts | TradingView Lightweight Charts |
| Backend deploy | Google Cloud Run |
| Frontend deploy | Vercel |
| Containerization | Docker (multi-stage, slim base) |
| CI/CD | GitHub Actions → Cloud Run |

---

## Key Technical Decisions

### WebSockets over polling

HTTP polling at 1-second intervals introduces 0–1000ms of additional detection latency by construction. WebSocket streams deliver order book updates within tens of milliseconds of market events. At the spreads this system targets (fractions of a percent of BTC price), detecting an opportunity at 50ms vs 800ms is often the difference between capturing it and missing it.

### In-memory BBO state, DuckDB for persistence

Embedding any database on the hot path — even an embedded one — adds microseconds to milliseconds of latency per event and introduces GIL contention when run from an async context. BBO state is a plain Python dict keyed by `Exchange` enum. It is never queried during detection or scoring.

DuckDB is used exclusively for analytics and audit: persisting the full trade log, latency statistics, and opportunity history. Writes happen in `asyncio.to_thread()` tasks that never block the event loop.

### Analytic position sizing vs greedy

A greedy sizer takes `min(available_depth_A, available_depth_B)` as the trade size. This ignores slippage: as size increases, the marginal spread narrows and slippage cost grows quadratically. The profit function `P(q) = q·net_spread − λ·q²` is strictly concave with a unique maximum at `q* = net_spread / (2λ)`. `OptimalSizer` computes this analytically, then clips to balance and depth constraints.

### USD ≠ USDT in triangular arbitrage

Most arbitrage systems treat USD and USDT as equivalent and find only trivial cycles. This engine feeds them as distinct graph nodes with an explicit conversion edge. The USD/USDT basis (typically 0.01–0.10%) creates real 3-currency triangles across exchanges that settle in different quote currencies — e.g., Binance (USDT) + Kraken (USD) + Bitstamp (USDT). Bellman-Ford detects these in O(V·E) without enumerating paths manually.

### Single event loop, no threading on the hot path

Python's asyncio model guarantees that only one coroutine runs at a time within a loop, eliminating the need for locks on shared BBO state. The scanner, scorer, sizer, and executor are all `async def` functions that yield only at explicit `await` points, which never appear in the numerical hot path. `gc.freeze()` at startup moves all existing objects to the permanent generation, eliminating GC pauses during steady-state operation.

---

## Evaluation Criteria Coverage

| Criterio | Implementación | Módulo / Archivo |
|---|---|---|
| **C1 · Velocidad** | WebSocket feeds en 7 exchanges — sin HTTP polling en ningún lugar | `data/adapters/*.py` |
| | Pipeline event-driven: un solo asyncio loop para todos los feeds | `api/main.py` |
| | uvloop 0.21 reemplaza el event loop por defecto (~2× throughput I/O) | `requirements.txt` |
| | orjson reemplaza stdlib json para parsing de mensajes (~3× más rápido) | `data/adapters/binance.py` |
| | `gc.freeze()` al startup — elimina GC pauses en estado estacionario | `api/main.py:514` |
| | **p50 decision latency < 5ms** medido end-to-end (`ws_received_at → executor_decided_at`) | `GET /api/metrics/latency` |
| **C2 · Precisión** | 4 componentes de costo: taker fee (buy) + taker fee (sell) + withdrawal + slippage cuadrático | `core/fees.py` |
| | Slippage dinámico desde profundidad de order book: `λ = spread_at_depth / volume` | `core/scanner.py` |
| | Latency risk buffer Almgren-Chriss: `k·σ·√Δt·q`, k = 1.6449 (z₀.₉₅) | `core/risk_buffer.py` |
| | Fill probability: `P(fill) = exp(−latency_ms / τ)` — ajusta E[profit] esperado | `core/fill_probability.py` |
| | `REJECTED_NEGATIVE_NET` registrado cuando `P(q*) ≤ 0` — nunca se ejecuta | `core/executor.py` |
| | Panel **Gross vs Net** en dashboard muestra el funnel de rechazo en tiempo real | `components/gross-net-panel.tsx` |
| **C3 · Robustez** | Circuit breaker: pausa ejecución 30s si `\|Δprice/price\| > 0.05%` en ventana 10s | `core/circuit_breaker.py` |
| | Revalidación pre-ejecución: precio re-chequeado antes de enviar orden | `core/executor.py` |
| | Partial fill guard: rechaza si profundidad disponible < 30% de `q*` | `core/executor.py` |
| | Liquidity health check: `LiquidityHealthMonitor` monitorea fragmentación por exchange | `core/liquidity_health.py` |
| | Stale quote rejection: quotes con `age > STALE_QUOTE_MS` (500ms) descartados en scorer | `core/scorer.py` |
| | 7 exchanges con depth monitoring simultáneo — sin punto único de falla | `data/adapters/` |
| **C4 · Estrategia** | Espacial: spread BTC cross-exchange, 42 pares dirigidos (7×6) evaluados cada tick | `core/scanner.py` |
| | Estadístico: OU z-score con estimación de half-life por AR(1) — `\|z\| > ENTRY_ZSCORE` | `core/stat_arb.py` |
| | Triangular: Bellman-Ford sobre log-rates, USD≠USDT como nodos distintos | `core/triangular.py` |
| | Portfolio allocator QP: `max rᵀx − λxᵀΣx` con wallet caps | `core/allocator.py` |
| | Sizing analítico: `q* = net_spread / (2λ)` — no greedy, no scanning | `core/sizer.py` |
| | Frecuencia de señal ajustada por freshness decay `exp(−age/200ms)` | `core/scorer.py` |
| **C5 · Calidad** | **244 tests** — sanity tests con valor esperado calculado a mano para cada función numérica pública | `tests/sanity/` |
| | Arquitectura modular: data / core / api / models / db — sin lógica de negocio en routes | `backend/` |
| | Todas las funciones públicas con type hints; modelos Pydantic v2 en API | `models/`, `api/routes/` |
| | DuckDB **nunca** en el hot path — escrituras en `asyncio.to_thread()` | `db/`, `api/main.py` |
| | Ruff para lint + format; funciones < 50 líneas; archivos < 300 líneas | `pyproject.toml` |
| **C6 · UI** | Dashboard Next.js 15 con datos en vivo vía WebSocket push (~100ms) | `frontend/app/page.tsx` |
| | **7 paneles distintos**: BBO prices, P&L chart, z-score OU, triangular arb, gross/net funnel, wallet rebalance, latency waterfall | `frontend/components/` |
| | Presentation mode (tecla `P`): layout limpio sin tablas, métricas en `text-6xl` | `components/price-ticker.tsx` |
| | TradingView Lightweight Charts para P&L y spread candlestick | `components/spread-chart.tsx` |
| | Circuit breaker toggle interactivo con countdown en vivo | `components/circuit-breaker-panel.tsx` |
| | Rebalance Status panel con barras de desviación por exchange y tier verde/amarillo/rojo | `components/rebalance-status.tsx` |

---

## References

- Almgren, R., & Chriss, N. (2000). *Optimal execution of portfolio transactions*. **Journal of Risk**, 3(2), 5–39. — Base para el latency risk buffer `k·σ·√Δt·q` implementado en `core/risk_buffer.py`.

- Avellaneda, M., & Lee, J. H. (2010). *Statistical arbitrage in the U.S. equities market*. **Quantitative Finance**, 10(7), 761–782. — Marco teórico del detector OU, z-score, y estimación de half-life en `core/stat_arb.py`.

- Gatev, E., Goetzmann, W. N., & Rouwenhorst, K. G. (2006). *Pairs trading: Performance of a relative-value arbitrage rule*. **Review of Financial Studies**, 19(3), 797–827. — Referencia para pairs selection y cointegración usada en el portfolio allocator.

- Bellman, R. (1958). *On a routing problem*. **Quarterly of Applied Mathematics**, 16(1), 87–90. — Algoritmo de detección de ciclos negativos en grafos de log-rates implementado en `core/triangular.py`.
