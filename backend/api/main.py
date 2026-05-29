from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.routes import circuit_breaker, health, metrics, opportunities, trades
from config import settings
from core import scanner, scorer
from core.circuit_breaker import get_circuit_breaker
from core.executor import simulate_execution
from core.sizer import InsufficientBalanceError, OptimalSizer
from data.adapters import binance, kraken, okx
import data.bbo_state as bbo_state_module
from db.connection import close_connection, get_connection
from db.schema import initialize_schema
from models.market import Exchange
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
        dead: set[WebSocket] = set()
        for client in self._clients:
            try:
                await client.send_text(data)
            except Exception:
                dead.add(client)
        self._clients -= dead


_ws_manager = ConnectionManager()
_sizer = OptimalSizer()

# ── pipeline loop ─────────────────────────────────────────────────────────────

async def _pipeline_loop() -> None:
    """scanner → scorer → sizer → executor, every 100ms."""
    _cb = get_circuit_breaker()

    while True:
        try:
            await asyncio.sleep(0.1)
            now = datetime.now(timezone.utc)

            if not _cb.allow_trade(now=now):
                continue

            bbo_state = bbo_state_module.get_all()
            if len(bbo_state) < 2:
                continue

            scan_started_at = datetime.now(timezone.utc)
            opportunities = scanner.scan_for_opportunities(bbo_state)
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
            trade = simulate_execution(top, qty, _wallets, bbo_state, now=decision_at)
            logger.info(
                "TRADE %-26s | %s→%s | qty=%.5f | net=$%+.2f",
                trade.status, trade.buy_exchange.value, trade.sell_exchange.value,
                trade.qty, trade.net_profit,
            )

            # Persist latency event (fire-and-forget, does not block hot path)
            trigger_bbo = bbo_state.get(top.buy_exchange)
            if trigger_bbo is not None:
                ws_recv = trigger_bbo.ws_received_at
                normalized = trigger_bbo.normalized_at
                total_ms = (decision_at - ws_recv).total_seconds() * 1000
                asyncio.create_task(asyncio.to_thread(
                    _persist_latency_event,
                    ws_recv, normalized, scan_started_at, decision_at, total_ms,
                ))
                logger.debug("Latency: %.2fms (ws→decision)", total_ms)

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
        asyncio.create_task(_pipeline_loop(), name="pipeline"),
    ]
    if settings.demo_mode:
        tasks.append(asyncio.create_task(_demo_loop(), name="demo"))
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


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket) -> None:
    await _ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _ws_manager.disconnect(websocket)
