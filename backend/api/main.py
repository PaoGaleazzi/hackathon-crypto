from __future__ import annotations

import asyncio
import gc
import json
import logging
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.routes import circuit_breaker, health, metrics, opportunities, trades, triangular
from config import settings
from core import scanner, scorer
from core.circuit_breaker import get_circuit_breaker
from core.executor import simulate_execution
from core.sizer import InsufficientBalanceError, OptimalSizer
from core.stat_arb import get_stat_arb_detector, signal_to_dict
from core.triangular import detect_triangular, set_latest_opportunities, triangular_to_dict
from data.adapters import binance, bitstamp, bybit, coinbase, gemini, kraken, okx
import data.bbo_state as bbo_state_module
from db.connection import close_connection, get_connection
from db.schema import initialize_schema
from models.market import BBO, Exchange
from models.trade import Trade, WalletBalance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── wallet state (simulation) ─────────────────────────────────────────────────

_INITIAL_USDT = 10_000.0
_INITIAL_BTC = 0.5

_wallets: dict[Exchange, WalletBalance] = {
    ex: WalletBalance(
        exchange=ex,
        usdt=_INITIAL_USDT,
        btc=_INITIAL_BTC,
        updated_at=datetime.now(timezone.utc),
    )
    for ex in Exchange
}

# ── WebSocket connection manager ──────────────────────────────────────────────

class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, data: str) -> None:
        clients = list(self._clients)
        if not clients:
            return
        results = await asyncio.gather(
            *(c.send_text(data) for c in clients),
            return_exceptions=True,
        )
        dead = {c for c, r in zip(clients, results) if isinstance(r, Exception)}
        self._clients -= dead


_ws_manager = ConnectionManager()
_sizer = OptimalSizer()

# ── statistical arbitrage monitoring ──────────────────────────────────────────

# z_score is broadcast at most this often; entry signals (|z|>2) fire immediately.
_STAT_ARB_BROADCAST_INTERVAL_S = 1.0
_last_zscore_broadcast: datetime | None = None


async def _update_stat_arb(bbo_state: dict[Exchange, BBO], now: datetime) -> None:
    """Feed the latest BBO spreads to the detector, broadcast entry signals
    immediately and the headline z-score at a throttled cadence.

    Runs every tick, independent of the circuit breaker and of whether any
    spatial opportunity exists — the z-score is market intelligence, not a trade.
    """
    global _last_zscore_broadcast
    detector = get_stat_arb_detector()
    signals = detector.update(bbo_state, now=now)

    for sig in signals:
        logger.info(
            "STAT-ARB SIGNAL | %s/%s | z=%+.2f | %s",
            sig.exchange_a.value, sig.exchange_b.value, sig.zscore, sig.direction.value,
        )
        await _ws_manager.broadcast(
            json.dumps({"type": "stat_arb_signal", "data": signal_to_dict(sig)})
        )

    throttled = (
        _last_zscore_broadcast is not None
        and (now - _last_zscore_broadcast).total_seconds() < _STAT_ARB_BROADCAST_INTERVAL_S
    )
    if throttled:
        return
    headline = detector.headline()
    if headline is not None:
        _last_zscore_broadcast = now
        await _ws_manager.broadcast(
            json.dumps({"type": "z_score", "data": {**headline, "timestamp": now.isoformat()}})
        )


# ── pipeline loop ─────────────────────────────────────────────────────────────

# Stat-arb is market intelligence, not hot path. Throttle its sampling to the
# prior cadence so the OU window's "ticks" keep their meaning and entry-signal
# broadcasts don't amplify when the loop wakes on every BBO update.
_STAT_ARB_SAMPLE_INTERVAL_S = 0.1

# Triangular opportunities are detected every tick (cheap, in-memory) but the
# top one is broadcast at most this often to avoid spamming the dashboard.
_TRIANGULAR_BROADCAST_INTERVAL_S = 0.5


async def _pipeline_loop() -> None:
    """Event-driven hot path: wakes on every BBO update (no fixed poll), then
    scanner → scorer → sizer → executor. ws→decision latency is measured with a
    monotonic clock (perf_counter_ns), immune to wall-clock/NTP skew.
    """
    _cb = get_circuit_breaker()
    update_event = bbo_state_module.get_update_event()
    last_stat_arb_mono = 0.0
    last_triangular_mono = 0.0

    while True:
        try:
            await update_event.wait()
            update_event.clear()
            now = datetime.now(timezone.utc)

            bbo_state = bbo_state_module.get_all()
            if len(bbo_state) < 2:
                continue

            mono = time.perf_counter()
            if mono - last_stat_arb_mono >= _STAT_ARB_SAMPLE_INTERVAL_S:
                last_stat_arb_mono = mono
                await _update_stat_arb(bbo_state, now)

            if not _cb.allow_trade(now=now):
                continue

            scan_started_at = datetime.now(timezone.utc)
            opportunities = scanner.scan_for_opportunities(bbo_state)

            # Triangular detection (USDT→BTC→USD→USDT) runs alongside the spatial
            # scan, independent of whether a spatial opportunity exists. Stored
            # every tick for GET /api/triangular; top one broadcast, throttled.
            triangular_opps = detect_triangular(bbo_state)
            set_latest_opportunities(triangular_opps)
            if triangular_opps and mono - last_triangular_mono >= _TRIANGULAR_BROADCAST_INTERVAL_S:
                last_triangular_mono = mono
                await _ws_manager.broadcast(json.dumps(
                    {"type": "triangular_opportunity", "data": triangular_to_dict(triangular_opps[0])}
                ))

            if not opportunities:
                continue

            ranked = scorer.rank_opportunities(opportunities, now=scan_started_at)
            top = ranked[0]

            balance_usdt = _wallets[top.buy_exchange].usdt
            try:
                qty = _sizer.compute_optimal_qty(top, balance_usdt)
            except InsufficientBalanceError:
                logger.warning("Insufficient balance on %s", top.buy_exchange.value)
                continue

            if qty <= 0:
                continue

            decision_at = datetime.now(timezone.utc)
            decision_ns = time.perf_counter_ns()
            trade = simulate_execution(top, qty, _wallets, bbo_state, now=decision_at)
            logger.info(
                "TRADE %-26s | %s→%s | qty=%.5f | net=$%+.2f",
                trade.status, trade.buy_exchange.value, trade.sell_exchange.value,
                trade.qty, trade.net_profit,
            )

            # Persist latency event (fire-and-forget, does not block hot path).
            # Latency is monotonic (ns); datetimes are stored only for display.
            trigger_bbo = bbo_state.get(top.buy_exchange)
            if trigger_bbo is not None:
                ws_recv = trigger_bbo.ws_received_at
                normalized = trigger_bbo.normalized_at
                ws_recv_ns = trigger_bbo.ws_received_ns
                total_ms = (
                    (decision_ns - ws_recv_ns) / 1e6
                    if ws_recv_ns is not None
                    else (decision_at - ws_recv).total_seconds() * 1000
                )
                asyncio.create_task(asyncio.to_thread(
                    _persist_latency_event,
                    ws_recv, normalized, scan_started_at, decision_at, total_ms,
                ))
                logger.debug("Latency: %.3fms (ws→decision, monotonic)", total_ms)

            prev_state = _cb.state
            _cb.record_trade(trade, now=decision_at)

            payload = json.dumps({"type": "trade", "data": trade.model_dump(mode="json")})
            await _ws_manager.broadcast(payload)

            if _cb.state != prev_state:
                cb_payload = json.dumps({"type": "circuit_breaker", "data": _cb.as_dict(now=decision_at)})
                await _ws_manager.broadcast(cb_payload)

        except asyncio.CancelledError:
            logger.info("Pipeline stopped")
            raise
        except Exception as exc:
            logger.exception("Pipeline error: %s", exc)


def _persist_latency_event(
    ws_received_at: datetime,
    normalized_at: datetime | None,
    scanned_at: datetime,
    decision_at: datetime,
    latency_ms: float,
) -> None:
    get_connection().execute(
        """
        INSERT INTO latency_events (ws_received_at, normalized_at, scanned_at, decision_at, latency_ms)
        VALUES (?, ?, ?, ?, ?)
        """,
        [ws_received_at, normalized_at, scanned_at, decision_at, latency_ms],
    )


# ── demo mode ─────────────────────────────────────────────────────────────────

_DEMO_PAIRS: list[tuple[Exchange, Exchange]] = [
    (Exchange.BINANCE, Exchange.KRAKEN),
    (Exchange.OKX,     Exchange.BINANCE),
    (Exchange.KRAKEN,  Exchange.COINBASE),
    (Exchange.BINANCE, Exchange.COINBASE),
    (Exchange.OKX,     Exchange.KRAKEN),
]
_DEMO_BTC_MID = 70_000.0


async def _demo_loop() -> None:
    """Inject synthetic executed trades every 10s for live demo presentations."""
    logger.info("DEMO MODE active — synthetic trades every 10s")
    while True:
        try:
            await asyncio.sleep(10.0)
            now = datetime.now(timezone.utc)

            buy_ex, sell_ex = random.choice(_DEMO_PAIRS)
            qty = round(random.uniform(0.05, 0.15), 4)
            net_profit = round(random.uniform(50.0, 200.0), 2)
            buy_price = _DEMO_BTC_MID
            # Back-calc sell price so that net_profit is exact (fees approximated)
            fee_buy = round(buy_price * qty * 0.001, 4)
            fee_sell_rate = 0.0026  # Kraken taker as conservative proxy
            sell_price = round((net_profit + buy_price * qty + fee_buy) / (qty * (1 - fee_sell_rate)), 2)
            fee_sell = round(sell_price * qty * fee_sell_rate, 4)

            trade = Trade(
                id=str(uuid.uuid4()),
                buy_exchange=buy_ex,
                sell_exchange=sell_ex,
                qty=qty,
                buy_price=buy_price,
                sell_price=sell_price,
                fee_buy=fee_buy,
                fee_sell=fee_sell,
                slippage_est=0.0,
                net_profit=net_profit,
                status="EXECUTED",
                ws_received_at=now,
                decision_at=now,
                latency_ms=round(random.uniform(15.0, 80.0), 2),
                executed_at=now,
            )

            await asyncio.to_thread(_persist_demo_trade, trade)

            logger.info(
                "DEMO TRADE | %s→%s | qty=%.4f BTC | net=$%.2f",
                buy_ex.value, sell_ex.value, qty, net_profit,
            )
            payload = json.dumps({"type": "trade", "data": trade.model_dump(mode="json")})
            await _ws_manager.broadcast(payload)

        except asyncio.CancelledError:
            logger.info("Demo loop stopped")
            raise
        except Exception as exc:
            logger.exception("Demo loop error: %s", exc)


def _persist_demo_trade(trade: Trade) -> None:
    get_connection().execute(
        """
        INSERT INTO trades (
            id, opportunity_id, buy_exchange, sell_exchange,
            qty, buy_price, sell_price, fee_buy, fee_sell,
            slippage_est, net_profit, status,
            ws_received_at, decision_at, latency_ms, executed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            trade.id, None,
            trade.buy_exchange.value, trade.sell_exchange.value,
            trade.qty, trade.buy_price, trade.sell_price,
            trade.fee_buy, trade.fee_sell,
            trade.slippage_est, trade.net_profit, trade.status,
            trade.ws_received_at, trade.decision_at,
            trade.latency_ms, trade.executed_at,
        ],
    )


# ── lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_schema()
    tasks = [
        asyncio.create_task(binance.run(), name="binance-ws"),
        asyncio.create_task(kraken.run(), name="kraken-ws"),
        asyncio.create_task(okx.run(), name="okx-ws"),
        asyncio.create_task(coinbase.run(), name="coinbase-ws"),
        asyncio.create_task(bybit.run(), name="bybit-ws"),
        asyncio.create_task(bitstamp.run(), name="bitstamp-ws"),
        asyncio.create_task(gemini.run(), name="gemini-ws"),
        asyncio.create_task(_pipeline_loop(), name="pipeline"),
    ]
    if settings.demo_mode:
        tasks.append(asyncio.create_task(_demo_loop(), name="demo"))

    # Move all startup objects into a permanent GC generation: collect once to
    # clear startup garbage, then freeze the survivors so the hot path's GC
    # cycles only scan new allocations — no long pauses on long-lived state.
    gc.collect()
    gc.freeze()

    logger.info("WS adapters + pipeline started (demo_mode=%s)", settings.demo_mode)
    yield
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    close_connection()
    logger.info("Shutdown complete")


# ── app ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="BTC Arbitrage Bot",
    version=settings.version,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(opportunities.router, prefix="/api")
app.include_router(trades.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(circuit_breaker.router, prefix="/api")
app.include_router(triangular.router, prefix="/api")


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await _ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_manager.disconnect(websocket)
