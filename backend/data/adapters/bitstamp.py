from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import orjson
import websockets

import data.bbo_state as bbo_state
from data.normalizer import normalize_bitstamp_bbo

logger = logging.getLogger(__name__)

_URL = "wss://ws.bitstamp.net"
_SUBSCRIBE_MSG = json.dumps({
    "event": "bts:subscribe",
    "data": {"channel": "order_book_btcusd"},
})
_MAX_BACKOFF_S = 60


async def run() -> None:
    """Connect to Bitstamp order_book_btcusd stream and keep BBO state updated."""
    backoff = 1
    while True:
        try:
            async with websockets.connect(_URL) as ws:
                await ws.send(_SUBSCRIBE_MSG)
                logger.info("Bitstamp WS connected and subscribed")
                backoff = 1
                async for raw_msg in ws:
                    received_at = datetime.now(timezone.utc)
                    received_ns = time.perf_counter_ns()
                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("Bitstamp: malformed JSON, skipping")
                        continue

                    bbo = normalize_bitstamp_bbo(data, received_at)
                    if bbo is not None:
                        bbo_state.update(bbo.model_copy(update={"ws_received_ns": received_ns}))

        except asyncio.CancelledError:
            logger.info("Bitstamp WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("Bitstamp WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
