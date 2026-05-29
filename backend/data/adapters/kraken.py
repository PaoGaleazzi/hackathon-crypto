from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import orjson
import websockets

import data.bbo_state as bbo_state
from core.liquidity_health import get_liquidity_monitor
from data.normalizer import normalize_kraken_bbo, normalize_kraken_depth
from models.market import Exchange

logger = logging.getLogger(__name__)

_URL = "wss://ws.kraken.com/v2"
_SUBSCRIBE_MSG = json.dumps({
    "method": "subscribe",
    "params": {
        "channel": "ticker",
        "symbol": ["BTC/USD"],
    },
})
_DEPTH_SUBSCRIBE_MSG = json.dumps({
    "method": "subscribe",
    "params": {
        "channel": "book",
        "symbol": ["BTC/USD"],
        "depth": 10,
    },
})
_MAX_BACKOFF_S = 60


async def run() -> None:
    """Connect to Kraken v2 ticker stream and keep BBO state updated."""
    backoff = 1
    while True:
        try:
            async with websockets.connect(_URL) as ws:
                await ws.send(_SUBSCRIBE_MSG)
                logger.info("Kraken WS connected and subscribed")
                backoff = 1
                async for raw_msg in ws:
                    received_at = datetime.now(timezone.utc)
                    received_ns = time.perf_counter_ns()
                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("Kraken: malformed JSON, skipping")
                        continue

                    bbo = normalize_kraken_bbo(data, received_at)
                    if bbo is not None:
                        bbo_state.update(bbo.model_copy(update={"ws_received_ns": received_ns}))

        except asyncio.CancelledError:
            logger.info("Kraken WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("Kraken WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)


async def run_depth() -> None:
    """Connect to Kraken v2 book channel and update the liquidity monitor."""
    backoff = 1
    monitor = get_liquidity_monitor()
    while True:
        asks_book: dict[float, float] = {}
        bids_book: dict[float, float] = {}
        try:
            async with websockets.connect(_URL) as ws:
                await ws.send(_DEPTH_SUBSCRIBE_MSG)
                logger.info("Kraken depth WS connected and subscribed")
                backoff = 1
                async for raw_msg in ws:
                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("Kraken depth: malformed JSON, skipping")
                        continue

                    asks = normalize_kraken_depth(data, asks_book, bids_book)
                    if asks is not None:
                        monitor.update(Exchange.KRAKEN, asks)

        except asyncio.CancelledError:
            logger.info("Kraken depth WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("Kraken depth WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
