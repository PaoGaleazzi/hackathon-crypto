from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import orjson
import websockets

import data.bbo_state as bbo_state
from data.normalizer import normalize_gemini_bbo

logger = logging.getLogger(__name__)

_URL = "wss://api.gemini.com/v1/marketdata/BTCUSD"
_MAX_BACKOFF_S = 60


async def run() -> None:
    """Connect to Gemini BTCUSD market data stream and keep BBO state updated.

    No subscription required — data flows on connect. The stream opens with a
    full snapshot as a series of change events, then sends incremental deltas.
    bids/asks are reset on each reconnect so the snapshot is always re-applied.
    """
    backoff = 1
    while True:
        try:
            async with websockets.connect(_URL) as ws:
                logger.info("Gemini WS connected")
                backoff = 1
                bids: dict[str, float] = {}
                asks: dict[str, float] = {}
                async for raw_msg in ws:
                    received_at = datetime.now(timezone.utc)
                    received_ns = time.perf_counter_ns()
                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("Gemini: malformed JSON, skipping")
                        continue

                    bbo = normalize_gemini_bbo(data, bids, asks, received_at)
                    if bbo is not None:
                        bbo_state.update(bbo.model_copy(update={"ws_received_ns": received_ns}))

        except asyncio.CancelledError:
            logger.info("Gemini WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("Gemini WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
