from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone

import orjson
import websockets

import data.bbo_state as bbo_state
from data.normalizer import normalize_okx_bbo

logger = logging.getLogger(__name__)

_URL = "wss://ws.okx.com:8443/ws/v5/public"
_SUBSCRIBE_MSG = json.dumps({
    "op": "subscribe",
    "args": [{"channel": "tickers", "instId": "BTC-USDT"}],
})
_MAX_BACKOFF_S = 60


async def run() -> None:
    """Connect to OKX v5 tickers stream and keep BBO state updated."""
    backoff = 1
    while True:
        try:
            async with websockets.connect(_URL) as ws:
                await ws.send(_SUBSCRIBE_MSG)
                logger.info("OKX WS connected and subscribed")
                backoff = 1
                async for raw_msg in ws:
                    received_at = datetime.now(timezone.utc)
                    received_ns = time.perf_counter_ns()

                    # OKX sends plain-text "ping" that requires a "pong" response
                    if raw_msg == "ping":
                        await ws.send("pong")
                        continue

                    try:
                        data = orjson.loads(raw_msg)
                    except orjson.JSONDecodeError:
                        logger.warning("OKX: malformed JSON, skipping")
                        continue

                    bbo = normalize_okx_bbo(data, received_at)
                    if bbo is not None:
                        bbo_state.update(bbo.model_copy(update={"ws_received_ns": received_ns}))

        except asyncio.CancelledError:
            logger.info("OKX WS adapter stopped")
            raise
        except Exception as exc:
            logger.warning("OKX WS error: %s — reconnecting in %ds", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)
