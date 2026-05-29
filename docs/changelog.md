# Changelog

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
