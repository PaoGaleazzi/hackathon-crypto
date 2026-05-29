# Task Queue — BTC Arbitrage Bot

## Cómo usar
1. Antes de abrir una instancia, revisa este archivo
2. Toma la primera tarea `[ ]` de tu área (backend/frontend/deploy)
3. Al terminar, cambia `[ ]` por `[x]` y agrega el resultado
4. Una instancia = una tarea = un módulo/archivo

---

## 🔴 Deploy (CRÍTICO — sin esto no entregas)
- [ ] Instalar gcloud CLI en Ubuntu
- [ ] `gcloud auth login` y configurar proyecto
- [ ] `bash scripts/deploy-backend.sh` — Cloud Run con --no-cpu-throttling --min-instances 1
- [ ] Deploy frontend a Vercel: `cd frontend && npx vercel --prod`
- [ ] Verificar URLs públicas funcionando
- [ ] Stress test en producción: 5 conexiones WS simultáneas

## 🟡 Backend pendiente
- [ ] Consolidar tests — mover backend/tests/sanity/ a tests/sanity/
- [ ] Bybit depth — solo data/adapters/bybit.py
- [x] Bitstamp depth — `run_depth()` + `normalize_bitstamp_depth`, task `bitstamp-depth`. Monitor cubre los 6 exchanges. 249 tests verdes.
- [ ] Stress test WebSocket local: 5 conexiones simultáneas
- [ ] Verificar que /api/status refleja todos los exchanges correctamente

## 🟢 Frontend pendiente
- [x] System health panel — `components/system-health-panel.tsx` + `useSystemHealth` (poll /api/status 5s). Muestra WS LIVE/OFFLINE + liquidity HEALTHY/DEGRADED/no-depth por exchange, uptime, trades, depth feeds, latencia p50. Completado a los 7 exchanges. Montado en dashboard. NOTE: `/api/status` devuelve `uptime_s=0` hardcoded → campo Uptime muestra "—" hasta wirear el start-time en backend.
- [ ] Verificar mobile responsive en todos los panels
- [ ] Screenshot del dashboard para el README

## ✅ Completado
- [x] 7 exchanges conectados (Binance, Kraken, OKX, Coinbase, Bybit, Bitstamp, Gemini)
- [x] Pipeline event-driven <5ms p50
- [x] Arbitraje estadístico OU (z-score)
- [x] Arbitraje triangular Bellman-Ford USD≠USDT
- [x] Portfolio allocator QP (mean-variance)
- [x] Latency risk buffer (Almgren-Chriss)
- [x] Fill probability con decay exponencial
- [x] Liquidity health check (4 exchanges con depth)
- [x] Circuit breaker
- [x] Order book depth + walk the book
- [x] Rebalancer MILP
- [x] 203+ tests
- [x] Dashboard con 7 panels
- [x] Presentation mode
- [x] README con Mathematical Foundations
