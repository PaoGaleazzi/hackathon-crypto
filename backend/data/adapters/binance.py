from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import orjson
import websockets

import data.bbo_state as bbo_state
from core.liquidity_health import get_liquidity_monitor
from data.normalizer import normalize_binance_bbo, normalize_binance_depth
from models.market import Exchange

logger = logging.getLogger(__name__)

_URL = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
_DEPTH_URL = "wss://stream.binance.com:9443/ws/btcusdt@depth10@100ms"
_MAX_BACKOFF_S = 60


async def run() -> None:
    """Connect to Binance bookTicker stream and keep BBO state updated."""
    backoff = 1
    while True:
        try:
            async with websockets.connect(_URL) as ws:
                logger.info("Binance WS connected")
                backoff = 1
                async for raw_msg in ws:
                    received_at = datetime.now(timezone.utc)
                    received_ns = time.perf_counter_ns()
                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("Binance: malformed JSON, skipping")
                        continue

                    bbo = normalize_binance_bbo(data, received_at)
                    if bbo is not None:
                        bbo_state.update(bbo.model_copy(update={"ws_received_ns": received_ns}))

        except asyncio.CancelledError:
            logger.info("Binance WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("Binance WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)


async def run_depth() -> None:
    """Connect to Binance @depth10@100ms stream and update the liquidity monitor."""
    backoff = 1
    monitor = get_liquidity_monitor()
    while True:
        try:
            async with websockets.connect(_DEPTH_URL) as ws:
                logger.info("Binance depth WS connected")
                backoff = 1
                async for raw_msg in ws:
                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("Binance depth: malformed JSON, skipping")
                        continue

                    result = normalize_binance_depth(data)
                    if result is None:
                        continue
                    bids, asks = result
                    # Feed asks (the side we buy from) into the monitor.
                    # Bids represent what we sell into — both sides matter for arb,
                    # but ask-side depth is the binding constraint for the buy leg.
                    monitor.update(Exchange.BINANCE, asks)

        except asyncio.CancelledError:
            logger.info("Binance depth WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("Binance depth WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
