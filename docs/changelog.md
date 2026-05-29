# Changelog

## 2026-05-29 (triangular wiring + allocator)
- feat(triangular): withdrawal cost en el modelo. `TriangularOpportunity` ahora lleva
  `notional`, `withdrawal_cost` (fee BTC × precio del venue de compra) y `net_profit`
  (= notional·(M-1) − withdrawal). `net_profit_pct` sigue size-independent (fees-only)
  y es el filtro de detección. `triangular_to_dict` para JSON; cache en memoria
  (`set/get_latest_opportunities`) — detección 100% en memoria, nunca DuckDB.
- feat(pipeline): `_pipeline_loop` corre `detect_triangular(bbo_state)` junto al scan
  espacial (antes del `if not opportunities`), guarda el latest cada tick y broadcasta
  el top con `{"type":"triangular_opportunity","data":{...}}` throttleado a 0.5s.
  NOTE: queda gated por el circuit breaker (vive después del `allow_trade`).
- feat(api): `GET /api/triangular` — últimas oportunidades triangulares desde el cache
  en memoria (sin DuckDB). Router en `api/routes/triangular.py`.
- feat(allocator): `core/allocator.py` — `optimize_allocation(...)` mean-variance con
  cvxpy. `maximize rᵀx − λ·xᵀΣx` s.t. `0≤x_i≤max_per_opp_i` y `Σ x_i ≤ cap_wallet`.
  Objetivo concavo (Σ PSD vía `psd_wrap`), fallback LP cuando λ=0. Devuelve
  `AllocationResult` (allocations, expected_profit, expected_variance, objective, status).
  Sanity tests en `tests/sanity/test_allocator.py` (9 casos: óptimo interior
  x*=r/(2λσ²), caps por wallet, wallet compartido, λ=0 LP, validaciones).
  NOTE: array-based; el mapeo opportunities→(r,Σ,wallet,max) y la estimación real de
  covarianza NO están incluidos (Σ requiere modelo de riesgo).

## 2026-05-29 (triangular)
- feat(triangular): `core/triangular.py` — `detect_triangular(bbo_state)` detecta
  arbitraje triangular real modelando el mercado como **grafo de divisas** donde
  USD y USDT son nodos DISTINTOS. Cada BBO aporta 2 edges (buy/sell BTC); las
  conversiones stablecoin (USDT↔USD) cierran el ciclo. Enumera ciclos dirigidos de
  3 monedas distintas (`USDT→BTC→USD→USDT`), nunca un espacial disfrazado. Costo de
  conversión configurable (`stablecoin_cost`, default 1bp). Devuelve lista ordenada
  por `net_profit_pct` desc. Dedup por rotación (canonicaliza a BUY-first).
  NOTE: modelo básico — netea solo los 3 legs (2 taker fees + 1 spread stablecoin);
  withdrawal de BTC entre venues y latencia/slippage NO incluidos.
  Sanity tests en `tests/sanity/test_triangular.py` (8 casos, caso conocido a mano:
  `0.999*0.9974*1.005 = 1.0013846`). NO está wireado al pipeline/API todavía.

## 2026-05-29 (latencia)
- perf(pipeline): `_pipeline_loop` ahora es **event-driven** — despierta con
  `bbo_state.get_update_event()` en vez de `asyncio.sleep(0.1)`. Elimina ~50ms de
  latencia promedio (0–100ms del polling) en el hot path espacial.
- perf(latency): latencia ws→decision medida con `time.perf_counter_ns()` (reloj
  monotónico, inmune a NTP/wall-clock skew). Nuevo campo `BBO.ws_received_ns`,
  sellado por los adapters vía `model_copy`. Los `datetime` se conservan solo para
  display/persistencia. NOTE: el leg `detected_at→now` del executor sigue en datetime
  (intra-proceso sub-ms).
- perf(stat-arb): el monitoreo OU se throttlea a `_STAT_ARB_SAMPLE_INTERVAL_S=0.1`
  dentro del loop event-driven, preservando la cadencia de sampling previa y evitando
  amplificar broadcasts de señales.
- perf(deps): `orjson` reemplaza `json.loads` en los 7 adapters WS (parse 2–5×).
  `uvloop` agregado a requirements — uvicorn lo auto-detecta con `--loop auto`.
- perf(ws): `ConnectionManager.broadcast` usa `asyncio.gather` (envío concurrente a
  todos los clientes, antes secuencial).
- perf(gc): `gc.collect()` + `gc.freeze()` tras el startup en `lifespan` — congela el
  estado de arranque para que los ciclos de GC del hot path solo escaneen allocs nuevas.
- ops(deploy): `scripts/deploy-backend.sh` añade `--no-cpu-throttling` (CPU siempre
  asignada, el event loop no se congela entre requests) y `--min-instances 1` (sin cold
  starts, WS persistentes).

## 2026-05-29 (cont.)
- refactor(config): `min_trade_size_btc` (0.001) centralizado en `settings`. `sizer.py`
  y `executor.py` lo consumen — antes divergían (0.001 vs 0.0001).
- refactor(executor): balance insuficiente y wallet ausente ahora devuelven
  `REJECTED_INSUFFICIENT_BALANCE` (nuevo literal en `TradeStatus`), no el engañoso
  `REJECTED_NEGATIVE_NET`.
- feat(api): `opportunities`, `trades`, `metrics` leen de DuckDB (implementados externamente,
  verificados vía smoke test). Endpoints: `/api/opportunities`, `/api/trades`, `/api/pnl`,
  `/api/metrics/summary`, `/api/metrics/latency`.
- fix(db): `SET TimeZone='UTC'` en la conexión DuckDB. `TIMESTAMPTZ`/`current_date` se
  renderizaban en tz local → JSON con offset no-UTC y `trade_count_today` mal bucketizado
  en la frontera de medianoche UTC.

## 2026-05-29
- feat(sizer): `OptimalSizer` en `core/sizer.py` — calcula `q*` (BTC) que maximiza
  ganancia neta de una `Opportunity` vía LP con cvxpy. Constraints: profundidad
  del order book, balance USDT del buy-side, `max_position_size` (1.0 BTC),
  `min_trade_size` (0.001 BTC). Lanza `InsufficientBalanceError` cuando el balance
  no cubre el mínimo. Reemplaza el stub `calculate_optimal_qty` (modelo de impacto
  Phase 3). Sanity tests en `tests/sanity/test_sizer.py` (8 casos). Dep nueva: cvxpy 1.9.1.
