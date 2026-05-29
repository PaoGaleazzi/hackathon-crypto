# Changelog

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
