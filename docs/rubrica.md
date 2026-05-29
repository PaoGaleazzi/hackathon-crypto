# Rúbrica del jurado — Guía de implementación

Fuente de verdad para priorizar trabajo. Revisar al inicio de cada fase.
Cada criterio tiene: qué construimos, en qué fase, cómo lo demostramos.

---

## Criterio 1 — Latencia de detección

> "¿Con qué latencia tu sistema identifica una divergencia desde que ocurre en el mercado? ¿Usas WebSockets? ¿Cómo optimizas el procesamiento en tiempo real?"

### Qué implementamos

- **WebSockets persistentes** para todos los exchanges (no polling). Un único `asyncio` event loop maneja todas las conexiones.
- **Pipeline de timestamps** encadenado en cada evento:
  `ws_received_at → normalized_at → scanned_at → decision_at`
- **BBO state en memoria** como dict puro. DuckDB nunca está en el hot path de detección — solo recibe writes async después de la decisión.
- **Métricas de latencia** (p50 / p95 / p99) calculadas sobre ventana deslizante de las últimas 1000 decisiones, expuestas vía REST y visibles en el dashboard.
- **Stale quote threshold**: si el BBO tiene >500ms de antigüedad, la oportunidad se marca `STALE` y no se ejecuta.

### Fases

| Fase | Entregable |
|------|------------|
| h0–h4 | WS adapters con `ws_received_at` en cada mensaje |
| h4–h8 | Pipeline completo de timestamps, persiste en DuckDB |
| h20–h36 | Dashboard muestra p50/p95 en tiempo real |

### Demo

Mostrar el widget de latencia en el dashboard con p50 y p95 actualizándose en vivo. Abrir DevTools y mostrar que el endpoint `/api/metrics/latency` devuelve números reales. Opcional: mostrar en código que no hay ningún `requests.get` ni `time.sleep` en el hot path.

### Checklist

- [ ] Todos los adapters usan WebSocket, ninguno usa polling HTTP
- [ ] Cada evento registra `ws_received_at` como primer timestamp
- [ ] DuckDB write ocurre en task separada, no bloquea el scanner
- [ ] `/api/metrics/latency` devuelve `{p50_ms, p95_ms, p99_ms}`
- [ ] Dashboard muestra latencia actualizada cada segundo

---

## Criterio 2 — Precisión de rentabilidad neta

> "¿Considera correctamente los fees de cada exchange, el slippage estimado y los riesgos de ejecución? ¿Evita ejecutar operaciones rentables en bruto pero negativas en neto?"

### Qué implementamos

- **Fee model por exchange** con tasas reales (taker fee de docs oficiales). Estructura: `FeeModel(exchange, taker_rate, withdrawal_btc_fixed)`.
- **Slippage model lineal** estimado del order book:
  `λ = spread_at_depth / total_volume_available`
  Se recalcula en cada tick, no es una constante hardcodeada.
- **Fórmula de profit neto** que el scanner evalúa antes de cualquier decisión:

  ```
  P(q) = q·(bid_B − ask_A)
       − q·ask_A·fee_A
       − q·bid_B·fee_B
       − λ·q²
       − W_fixed
  ```

- **Optimal q\*** analítico (dP/dq = 0):
  `q* = (net_spread) / (2λ)`
  con constraints: `q ≤ min(depth_A, depth_B, balance_usdt/ask_A, balance_btc_B)`
- **Threshold mínimo de rentabilidad**: solo ejecutar si `P(q*) > MIN_PROFIT_USD` (configurable, default $1).
- Toda oportunidad registrada en DuckDB incluye el desglose completo: gross, fee_A, fee_B, slippage, net.

### Fases

| Fase | Entregable |
|------|------------|
| h0–h4 | Fee model estático (tasas hardcodeadas de docs oficiales) |
| h4–h8 | Profit neto con fees en cada oportunidad registrada |
| h8–h20 | Slippage dinámico del order book + OptimalSizer |

### Demo

Seleccionar un trade del historial y mostrar el desglose: precio bruto → fee compra → fee venta → slippage estimado → profit neto. Mostrar un caso donde el sistema detectó una oportunidad pero la descartó porque el neto era negativo (evento `REJECTED_NEGATIVE_NET`).

### Checklist

- [ ] `FeeModel` tiene tasas reales de Binance, Kraken y Coinbase (verificadas contra docs oficiales)
- [ ] Slippage estimado desde profundidad del order book, no constante
- [ ] `q*` calculado analíticamente, no es "max available"
- [ ] Oportunidades con neto ≤ 0 se registran como `REJECTED_NEGATIVE_NET`
- [ ] Cada trade en DuckDB tiene columnas: `gross_spread`, `fee_buy`, `fee_sell`, `slippage_est`, `net_profit`

---

## Criterio 3 — Robustez

> "¿Cómo maneja baja liquidez, órdenes parciales o movimientos bruscos durante la ejecución? ¿Existe mecanismo de circuit breaker?"

### Qué implementamos

**Partial fills**
- El ejecutor opera `min(ask_depth_A, bid_depth_B, q*)`. Si eso cubre < `MIN_FILL_RATIO` (default 30%) del q* óptimo, aborta: el costo fijo de withdrawal no se amortiza.
- Registra el fill ratio real en cada trade.

**Stale quote abort**
- Pre-ejecución, re-verifica que el spread sigue siendo positivo con precios actuales. Si colapsó desde la detección, registra `ABORTED_STALE` y no ejecuta.

**Circuit breaker por volatilidad**
- Calcula volatilidad realizada en ventana de 10s sobre el mid-price de BTC.
- Si `|Δprice / price| > CIRCUIT_THRESHOLD` (default 0.05%) en esa ventana, el circuit breaker se abre por `COOLDOWN_SECONDS` (default 30s).
- Estado visible en dashboard: `OPEN` / `CLOSED` con countdown.

**Balance simulation correcta**
- Wallet state por exchange: `{USDT: float, BTC: float}`.
- El ejecutor bloquea si el balance insuficiente, registra `REJECTED_INSUFFICIENT_BALANCE`.
- Balances se actualizan atómicamente (no hay race condition en el event loop único).

### Fases

| Fase | Entregable |
|------|------------|
| h8–h20 | ExecutionSimulator completo con los cuatro mecanismos |
| h20–h36 | Estado del circuit breaker visible en dashboard |

### Demo

Forzar el circuit breaker manualmente bajando el umbral a 0.001% para que se active. Mostrar en el dashboard que el estado cambia a `OPEN` y las ejecuciones se pausan. Mostrar en el historial eventos `ABORTED_STALE` y `SKIPPED_MIN_FILL` — el bot sabe cuándo no operar.

### Checklist

- [ ] Partial fills ejecutan `min(depth_A, depth_B, q*)`, nunca exceden liquidez disponible
- [ ] Trades con fill < `MIN_FILL_RATIO` se registran como `SKIPPED_MIN_FILL`
- [ ] Pre-ejecución revalida precio actual; aborta si spread colapsó
- [ ] Circuit breaker detecta volatilidad spike en ventana 10s
- [ ] Estado del circuit breaker (`OPEN`/`CLOSED`) expuesto en `/api/status`
- [ ] Dashboard muestra estado del circuit breaker en tiempo real
- [ ] Wallet balances no pueden quedar negativos

---

## Criterio 4 — Inteligencia y estrategia

> "¿El sistema prioriza y compara múltiples oportunidades? ¿Implementa estrategias más sofisticadas como arbitraje triangular o estadístico?"

### Qué implementamos

**Multi-exchange scanning**
- Mínimo 3 exchanges: Binance, Kraken, Coinbase.
- Scanner evalúa todos los pares posibles: N exchanges → N·(N−1)/2 pares simultáneos.
- 3 exchanges = 3 pares. 4 exchanges = 6 pares. Escala sin cambios en la lógica.

**OpportunityScorer — priority queue con score compuesto**

```
score = net_spread_pct
      × available_liquidity_btc
      × freshness_decay(age_ms)       # e^(−age_ms / 200)
      − volatility_penalty(σ_10s)
```

El ejecutor toma siempre la oportunidad de mayor score, no la primera detectada.

**OptimalSizer** (ver Criterio 2) — diferenciador matemático frente a bots greedy.

**Stretch goal — Arbitraje estadístico entre exchanges**
Si hay tiempo en Fase 4: detectar divergencias persistentes entre el mid-price de dos exchanges usando z-score sobre ventana rodante. Si `z > 2.0`, señal de mean reversion. Esto va más allá del arbitraje puro.

### Fases

| Fase | Entregable |
|------|------------|
| h0–h4 | Scanner para 2 exchanges (base) |
| h8–h20 | OpportunityScorer + 3er exchange + OptimalSizer |
| h20–h36 | 4to exchange si el tiempo lo permite |
| h36–h48 | Arbitraje estadístico (stretch) |

### Demo

Mostrar el dashboard con 3+ exchanges activos y múltiples oportunidades rankeadas simultáneamente. Señalar que el bot ejecutó la oportunidad #3 de la lista, no la #1, porque tenía mejor liquidez. Mostrar el score compuesto en la UI.

### Checklist

- [ ] Mínimo 3 exchanges conectados via WebSocket
- [ ] Scanner evalúa todos los pares N·(N−1)/2 en cada tick
- [ ] `OpportunityScorer` produce un score compuesto (no solo spread bruto)
- [ ] El ejecutor consume de una priority queue, no de una lista FIFO
- [ ] `OptimalSizer` calcula q* analítico, documentado con la fórmula
- [ ] Dashboard muestra las top-N oportunidades activas rankeadas

---

## Criterio 5 — Calidad de arquitectura y código

> "¿El sistema está bien estructurado, es mantenible y escalable? ¿El código es legible, documentado, sigue buenas prácticas?"

### Qué implementamos

**Estructura de módulos**

```
backend/
  data/        # WS adapters, normalizer, BBO state
  core/        # scanner, scorer, sizer, executor
  api/         # FastAPI routes (thin wrappers)
  models/      # Pydantic models compartidos
  db/          # DuckDB schema + queries
tests/
  sanity/      # un test por función numérica con caso conocido
frontend/
  app/         # Next.js App Router
  components/  # UI components
```

**Estándares no negociables**
- Type hints en toda función pública de Python.
- Pydantic models para todos los request/response de la API.
- Funciones < 50 líneas, archivos < 300 líneas.
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`.
- `.env.example` actualizado con todas las variables.
- Sanity tests para toda función numérica: `OpportunityScorer`, `OptimalSizer`, fee calculations.

**README**
- Diagrama de arquitectura (ASCII o imagen).
- Instrucciones de setup en < 5 comandos.
- Decisiones técnicas clave documentadas.
- Link al deploy.

### Fases

| Fase | Entregable |
|------|------------|
| h0–h4 | Estructura de directorios definida, no se cambia después |
| h0–h48 | Convenciones aplicadas en cada commit |
| h36–h48 | README completo, sanity tests para módulos core |

### Checklist

- [ ] Estructura de módulos respeta la separación data/core/api
- [ ] Cero funciones públicas sin type hints en Python
- [ ] Cero rutas de FastAPI con lógica de negocio inline
- [ ] Sanity tests para: fee calculation, profit neto, optimal q*, scorer
- [ ] `pytest -x` pasa sin errores antes del deploy final
- [ ] README tiene diagrama de arquitectura e instrucciones de setup
- [ ] `.env.example` tiene todas las variables necesarias
- [ ] Commits siguen Conventional Commits

---

## Criterio 6 — UI web desplegada

> "Solución desplegada y funcional. Interfaz que permita visualizar estado del mercado, oportunidades detectadas, operaciones ejecutadas y P&L acumulado."

### Qué implementamos

**Componentes del dashboard** (Next.js 15 + shadcn/ui):

| Componente | Datos | Actualización |
|------------|-------|---------------|
| Price feed table | BBO de cada exchange | WS push, ~100ms |
| Opportunity queue | Top-5 oportunidades activas con score | WS push |
| Trade log | Historial de trades con desglose | REST polling 2s |
| P&L chart | Cumulative P&L acumulado | TradingView Lightweight Charts |
| System status | Latencia p95, circuit breaker, exchanges conectados | WS push |
| Wallet balances | USDT y BTC por exchange | WS push |

**Arquitectura de actualización**
- Backend expone `/ws/live` que pushea eventos al frontend.
- Frontend no hace polling para datos en tiempo real — solo para historial.
- Reconexión automática si el WS se cae.

**Deploy**
- Backend: Cloud Run (Dockerfile + `gcloud run deploy`).
- Frontend: Vercel (Next.js deploy más rápido) o Cloud Run si se prefiere un solo proveedor.
- URL pública disponible antes de h40 para tener buffer de debug.

### Fases

| Fase | Entregable |
|------|------------|
| h4–h8 | UI mínima: tabla de oportunidades, datos via REST |
| h8–h20 | WebSocket push del backend, datos en tiempo real |
| h20–h36 | P&L chart, system status, wallet balances |
| h36–h48 | Polish, mobile-responsive, URL pública estable |

### Demo

La demo ocurre en el browser, no en el código. Flujo de demo:
1. Abrir dashboard — jurado ve exchanges conectados y precios en vivo.
2. Señalar la opportunity queue — top oportunidades rankeadas actualizándose.
3. Esperar o forzar un trade — mostrar cómo el trade log se actualiza y el P&L sube.
4. Mostrar el P&L chart con la curva acumulada.
5. Mostrar el widget de latencia p95.
6. Abrir el circuit breaker manualmente — mostrar que el sistema se pausa.

### Checklist

- [ ] Dashboard carga en < 3 segundos desde URL pública
- [ ] Price feed muestra BBO de 3+ exchanges actualizándose en tiempo real
- [ ] Opportunity queue muestra oportunidades rankeadas con score visible
- [ ] Trade log muestra desglose: gross, fees, slippage, net
- [ ] P&L chart (TradingView) muestra curva acumulada
- [ ] System status muestra latencia p95 y estado del circuit breaker
- [ ] Wallet balances visibles por exchange
- [ ] Frontend se reconecta automáticamente si el WS se cae
- [ ] URL pública accesible antes de h40

---

## Resumen por fase

| Fase | Criterios principales atendidos |
|------|--------------------------------|
| h0–h4 | C1 (WS adapters), C2 (fee model), C5 (estructura) |
| h4–h8 | C1 (timestamps), C2 (neto en DB), C6 (UI mínima deployada) |
| h8–h20 | C2 (slippage+sizer), C3 (executor+circuit breaker), C4 (scorer) |
| h20–h36 | C4 (4to exchange), C6 (dashboard completo) |
| h36–h48 | C5 (README+tests), C6 (polish+URL estable) |

> Regla: antes de pasar de fase, hacer un mini-review contra los checklist de los criterios que esa fase cubría.
