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
from data.normalizer import normalize_coinbase_bbo, normalize_coinbase_depth
from models.market import Exchange

logger = logging.getLogger(__name__)

_URL = "wss://advanced-trade-ws.coinbase.com/ws"
_SUBSCRIBE_MSG = json.dumps({
    "type": "subscribe",
    "product_ids": ["BTC-USD"],
    "channel": "ticker",
})
_DEPTH_SUBSCRIBE_MSG = json.dumps({
    "type": "subscribe",
    "product_ids": ["BTC-USD"],
    "channel": "level2",
})
_MAX_BACKOFF_S = 60


async def run() -> None:
    """Connect to Coinbase Advanced Trade ticker stream and keep BBO state updated."""
    backoff = 1
    while True:
        try:
            async with websockets.connect(_URL) as ws:
                await ws.send(_SUBSCRIBE_MSG)
                logger.info("Coinbase WS connected and subscribed")
                backoff = 1
                async for raw_msg in ws:
                    received_at = datetime.now(timezone.utc)
                    received_ns = time.perf_counter_ns()
                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("Coinbase: malformed JSON, skipping")
                        continue

                    bbo = normalize_coinbase_bbo(data, received_at)
                    if bbo is not None:
                        bbo_state.update(bbo.model_copy(update={"ws_received_ns": received_ns}))

        except asyncio.CancelledError:
            logger.info("Coinbase WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("Coinbase WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)


async def run_depth() -> None:
    """Connect to Coinbase level2 stream and update the liquidity monitor."""
    backoff = 1
    monitor = get_liquidity_monitor()
    while True:
        asks_book: dict[float, float] = {}
        try:
            async with websockets.connect(_URL) as ws:
                await ws.send(_DEPTH_SUBSCRIBE_MSG)
                logger.info("Coinbase depth WS connected and subscribed")
                backoff = 1
                async for raw_msg in ws:
                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("Coinbase depth: malformed JSON, skipping")
                        continue

                    asks = normalize_coinbase_depth(data, asks_book)
                    if asks is not None:
                        monitor.update(Exchange.COINBASE, asks)

        except asyncio.CancelledError:
            logger.info("Coinbase depth WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("Coinbase depth WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
