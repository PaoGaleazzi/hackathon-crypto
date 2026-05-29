from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import orjson
import websockets

import data.bbo_state as bbo_state
from data.normalizer import normalize_binance_bbo

logger = logging.getLogger(__name__)

_URL = "wss://stream.binance.com:9443/ws/btcusdt@bookTicker"
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
