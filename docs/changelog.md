# Changelog

## 2026-05-29 (computed_at en WS + stress test)
- feat(api): el broadcast WS `{"type":"rebalance"}` ahora incluye `computed_at`
  (`_rebalance_to_dict(plan, decision_at)`) — el mismo timestamp que se guarda en cache,
  así el payload WS coincide 1:1 con `GET /api/rebalance` y el cliente tiene el timestamp
  exacto del server en tiempo real. `useRebalance` usa `data.computed_at` (fallback a
  client time solo si falta).
- test(stress): backend con `DEMO_MODE=true`, 5+ conexiones WS simultáneas a `/ws/live`:
  - **Fan-out correcto**: los 5 clientes reciben mensajes idénticos (10 hashes únicos =
    10 comunes a todos), en lockstep (±23ms).
  - **Latencia estable con N clientes**: skew fan-out (max-min recv del MISMO mensaje)
    N=1→0ms, N=5→0.10ms, N=10→0.20ms, N=20→0.75ms medio / 1.48ms máx. Sublineal, negligible.
  - **Sin memory leak**: RSS 238→243 MB tras 120 ciclos connect/disconnect, plateau estable
    (olas 4-6: 243/242/243 MB). El handler limpia en `WebSocketDisconnect` y `broadcast`
    poda clientes muertos en fallo de envío (doble cleanup).
  - **Cero errores** en el path broadcast/`ConnectionManager`/pipeline.
  - NOTE: detectados 2 bugs PRE-EXISTENTES no relacionados, en adapters de datos upstream:
    (1) normalizer de Coinbase espera `best_bid_size` pero el ticker trae `best_bid_quantity`
    → ~1000 warnings de parseo, BBO de Coinbase nunca actualiza; (2) Coinbase depth (level2)
    excede el `max_size` default de websockets → `1009 message too big` + reconexión en loop.
- test: 249/249 verdes (suite consolidada en `tests/` raíz por otra instancia).

## 2026-05-29 (Bybit depth)
- feat(bybit): `run_depth()` suscribe a `orderbook.10.BTCUSDT`. `normalize_bybit_depth`
  maneja snapshot (clear + rebuild desde `data.a`) y delta (deltas qty=0→remove).
  Estado `asks_book` en-memoria, reset por reconexión. Registrado como `"bybit-depth"`.
  Monitor cubre ahora Binance, Kraken, OKX, Coinbase, Bybit.
- 249/249 tests verdes.

## 2026-05-29 (Coinbase depth)
- feat(coinbase): `run_depth()` suscribe al canal `level2`. `normalize_coinbase_depth`
  maneja snapshot (clear + rebuild desde `asks[]`) y l2update (deltas `side="sell"` en
  `changes[]`). Estado `asks_book` en-memoria, reset por reconexión. Registrado en
  lifespan como `"coinbase-depth"`. Monitor cubre ahora Binance, Kraken, OKX, Coinbase.
- 46/46 tests verdes.

## 2026-05-29 (rebalance plan en dashboard)
- feat(api): `GET /api/rebalance` — último plan de rebalanceo desde un cache en memoria
  (`set_latest_plan`/`get_latest_plan` en `core/rebalancer.py`, mismo patrón que triangular).
  Devuelve `status` (OK/BALANCED/INFEASIBLE/NONE), `total_cost_usd`, `transfers[]` y
  `computed_at` ISO. El pipeline escribe el plan cada `_REBALANCE_EVERY_N_TRADES`; "NONE"
  hasta el primer cálculo. Router en `api/routes/rebalance.py`, montado con prefix `/api`.
- feat(frontend): hook `useRebalance` (poll `/api/rebalance` cada 2s + WS `rebalance`) y
  `PendingPlanPanel` dentro de `RebalanceStatus`: lista las transferencias recomendadas
  (asset, from→to, amount, fee), costo estimado en USD y botón "Apply Rebalance" SOLO
  visual (no ejecuta nada). Se muestra solo cuando `status==='OK'` con transfers. La grid
  de deviation por exchange existente queda intacta.
- test: 46/46 backend verdes; `tsc --noEmit` y eslint limpios en los archivos nuevos.

## 2026-05-29 (OKX depth)
- feat(okx): `run_depth()` suscribe al canal `books5` de OKX v5. `normalize_okx_depth`
  extrae asks `[price, qty, ...]` del snapshot completo (books5 no hace updates
  incrementales, no requiere estado). Registrado en lifespan como `"okx-depth"`.
- 46/46 tests verdes.

## 2026-05-29 (Kraken depth + degraded_liquidity en dashboard)
- feat(kraken): `run_depth()` suscribe al canal `book` depth=10 de Kraken v2. Mantiene
  estado en-memoria `asks_book/bids_book` (reset en cada reconexión). `normalize_kraken_depth`
  maneja snapshot (clear + rebuild) y updates (deltas qty=0→remove), retorna top-10 asks
  ordenados. Alimenta `monitor.update(KRAKEN, asks)` en cada mensaje.
- feat(api): `GET /api/opportunities` ahora incluye `degraded_liquidity: bool` por row,
  computado en query-time desde el monitor (refleja estado *actual* del libro, no histórico).
- feat(frontend): `Opportunity.degraded_liquidity?: boolean` en el tipo. La columna ROUTE
  muestra ⚠️ con `title="Liquidez fragmentada detectada"` cuando el flag está activo.
- refactor(main): `kraken-depth` registrado como task en lifespan.
- 46/46 tests verdes.

## 2026-05-29 (variance inflation + rebalancer wiring)
- feat(allocator): la diagonal de la covarianza ahora es `σ_i² = r_i² / P_fill_i`
  (antes `r_i²`). El factor 1/P_fill infla el riesgo percibido de opps stale, que ya
  pagaban menor retorno vía `expected_profit` → penalización DOBLE (menor media Y mayor
  varianza). El óptimo interior pasa a `x* = P_fill·/(2λ·r_i)`, starveando spreads viejos
  por ambos términos. Floor `max(P_fill, 1e-9)` evita divide-by-zero cuando P_fill hace
  underflow a 0.0 con latencia alta. Triangular sin modelo de decay → P_fill=1.
- feat(pipeline): rebalanceo wireado al hot path. Cada `_REBALANCE_EVERY_N_TRADES=25`
  trades EXECUTED se planea un `plan_rebalance` hacia un target de split parejo
  (`_even_split_targets`: total de cada asset ÷ n wallets), corrido off-loop vía
  `asyncio.to_thread` (el MILP es CPU-bound). El plan se broadcasta `{"type":"rebalance"}`
  como advisory — la sim NO ejecuta las transferencias (evita race con el hot path y
  respeta el diseño planner del módulo). `btc_price` = mid medio cross-exchange.
- test: 5 sanity tests de varianza/retorno (`σ_i²=r_i²/P_fill`, stale más riesgosa que
  fresh por |retorno|). 46/46 verdes.
- NOTE: instancia 3 (`core/rebalancer.py`) ya estaba terminada y autónoma; solo la conecté
  al pipeline. Su fix paralelo de `test_allocator.py` (pasar `now`) ya estaba aplicado.

## 2026-05-29 (rebalancer)
- feat(rebalancer): `core/rebalancer.py` — `plan_rebalance(wallets, targets, btc_price)`
  resuelve el rebalanceo de wallets como **fixed-charge min-cost flow**. Nodos =
  (exchange, asset); edges = transferencias same-asset con su withdrawal fee FIJA por
  transferencia. Objetivo: minimizar Σ fee(source)·y_e (y_e binaria "ruta usada");
  constraint: cada wallet final dentro de ±`band` del target. Decompone por asset
  (BTC/USDT), devuelve `RebalancePlan` (transfers, total_cost_usd, status OK/BALANCED/
  INFEASIBLE). NOTE: usa `scipy.optimize.milp`, NO linprog/min_cost_flow — las fees son
  fijas por transferencia (fixed-charge), que un LP per-unit no modela (un fee plano de
  ~$1 de USDT tratado por-unidad daría costo absurdo). Flujos conservan el asset; el fee
  se cuenta como costo USD aparte. Llamada periódica, no por tick. Sanity tests en
  `tests/sanity/test_rebalancer.py` (8 casos: rebalanceo conocido 0.5 BTC=$50, sin acción
  dentro de banda, fuente más barata Kraken<Gemini, infeasible por sumas, USDT flat,
  multi-asset, validaciones).
- fix(test): `test_allocator.py` adapter tests pasan `now=_NOW` — el refactor en paralelo
  de `build_allocation_inputs` (retorno espacial ponderado por fill-probability vía
  `expected_profit`) volvía la oportunidad "vieja" sin `now`; con `now=detected_at` el
  p_fill=1 recupera `r=net_spread/capital`.

## 2026-05-29 (liquidity health pipeline integration)
- feat(binance): stream `@depth10@100ms` en `run_depth()`. Parsea top-10 asks vía
  `normalize_binance_depth` y alimenta el monitor cada 100ms. Registrado en lifespan
  como task `"binance-depth"`.
- feat(scanner): consulta `get_liquidity_monitor().is_healthy()` para buy y sell exchange.
  Si alguno DEGRADED → `Opportunity.degraded_liquidity=True`. No se descarta.
- feat(scorer): `DEGRADED_LIQUIDITY_PENALTY=0.5`. Score final ×0.5 cuando
  `opportunity.degraded_liquidity`. Refleja slippage latente que BBO no captura.
- refactor(models): `Opportunity.degraded_liquidity: bool = False` (retro-compatible).
- 44/44 tests verdes.

## 2026-05-29 (E[profit] → allocator)
- feat(allocator): `build_allocation_inputs` usa `expected_profit(opp, now)` como
  expected_return de los legs espaciales (r_i = E[profit]/capital_basis), ya no
  `net_spread` bruto. El QP ahora reparte capital ponderando por probabilidad de fill:
  una oportunidad stale obtiene r_i ≈ 0 (o negativo) y queda starved (x_i=0 con x≥0).
  Nuevos params `now`/`tau_ms` (default `now=utcnow`, `tau=DEFAULT_TAU_MS`).
- test: 3 sanity tests (r_i = E[profit]/capital, fresh > stale con mismo spread,
  stale con E[profit]<0 → r_i<0). 44/44 verdes.
- NOTE: scorer.py NO tenía cambios de la instancia 1 (latency buffer); su trabajo vive
  en `core/risk_buffer.py` (gate Almgren-Chriss autónomo). Sin conflicto, sin reconciliar.

## 2026-05-29 (liquidity health monitor)
- feat(liquidity_health): `core/liquidity_health.py`. Detector de fragmentación de order
  book inspirado en econofísica. `compute_fragmentation_score(levels, top_n=10)` — O(N).
  Fórmula: `Σ (rel_gap_i / qty_i) / total_depth`, donde rel_gap_i es el gap normalizado
  por el mejor precio y qty_i el volumen en el nivel i. Libros sanos ≈ 1e-5; fragmentados
  ≈ 0.1–10+. `LiquidityHealthMonitor` (singleton) cachea el estado por exchange y expone
  `is_healthy(exchange)` para que el pipeline evite legs en exchanges DEGRADED.
- feat(api): `GET /api/status` ahora incluye `liquidity_health` con score, status
  (HEALTHY/DEGRADED/UNKNOWN), level_count y computed_at por exchange.
- test: 15 sanity tests — valores conocidos a mano para libro sano (score=3e-5) y
  fragmentado (score=0.75), invariantes de monotonía, truncación top_n, estado del monitor.
  41/41 verdes.

## 2026-05-29 (fill-probability model)
- feat(fill_probability): nuevo `core/fill_probability.py`. Modela que las oportunidades
  más viejas tienen menor probabilidad de seguir en el book cuando llega nuestra orden.
  `P_fill(latency) = exp(-latency_ms / tau)`, tau configurable (default 50ms → P_fill=1/e
  a un tau de antigüedad). `E[profit] = P_fill·net_profit - (1-P_fill)·penalty`, donde la
  penalty default es el sunk cost de una ejecución fallida (taker fees de ambos legs vía
  `core/fees`). Oportunidades stale pueden scorear negativo y salir de la cola.
- refactor(scorer): `score_opportunity` rankea por E[profit] ajustado (× liquidity_score),
  ya no por profit bruto sobre latencia cruda. `tau_ms` propagado por `rank_opportunities`.
- test: 8 sanity tests nuevos (decay de P_fill, E[profit] conocido a mano, fresh > stale
  con mismo spread, penalty = suma de taker fees). 26/26 verdes.

## 2026-05-29 (allocator wiring + frontend)
- feat(allocator): `build_allocation_inputs(spatial, triangular, wallets)` arma los
  inputs del QP desde oportunidades vivas. r_i = retorno neto por unidad de capital
  (spatial: `net_spread/(qty·ask)`; triangular: `net_profit_pct/100`). Σ diagonal con
  proxy `σ_i² = r_i²` — el óptimo interior `x*=1/(2λr)` da MENOS capital a spreads
  anchos (típicamente stale), diversificando. `allocation_to_dict` para el broadcast.
- feat(pipeline): el hot path ya no toma `ranked[0]`. Corre la allocación mean-variance
  sobre TODAS las oportunidades simultáneas, broadcasta `{"type":"allocation",...}` con
  la vista de portfolio y ejecuta los legs espaciales con el capital asignado (qty =
  capital/ask, ≥ min_trade_size). Triangular va solo en la vista (sin executor aún).
  Se removió `OptimalSizer`/`scorer` del loop.
- feat(frontend): panel de triángulos. Hook dedicado `useTriangular` (poll `/api/triangular`
  cada 2s + WS `triangular_opportunity`), `components/triangular-panel.tsx` (tabla:
  triángulo, buy/sell venue, profit %, net P&L, withdrawal). Montado en dashboard y en
  la vista Opportunities. Next 16: solo client components/hooks (sin tocar SSR/data-fetch).

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
