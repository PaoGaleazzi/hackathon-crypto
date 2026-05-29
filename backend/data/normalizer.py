from __future__ import annotations

import logging
from datetime import datetime, timezone

from models.market import BBO, Exchange

logger = logging.getLogger(__name__)


def normalize_binance_bbo(raw: dict, received_at: datetime) -> BBO | None:
    """Parse Binance bookTicker WS message into BBO."""
    try:
        bid = float(raw["b"])
        ask = float(raw["a"])
        bid_qty = float(raw["B"])
        ask_qty = float(raw["A"])
    except (KeyError, ValueError) as exc:
        logger.warning("Binance: failed to parse BBO: %s — raw: %s", exc, raw)
        return None

    if bid <= 0 or ask <= 0 or bid_qty <= 0 or ask_qty <= 0:
        logger.warning("Binance: invalid BBO values bid=%s ask=%s bid_qty=%s ask_qty=%s", bid, ask, bid_qty, ask_qty)
        return None

    return BBO(
        exchange=Exchange.BINANCE,
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        ws_received_at=received_at,
        normalized_at=datetime.now(timezone.utc),
    )


def normalize_kraken_bbo(raw: dict, received_at: datetime) -> BBO | None:
    """Parse Kraken v2 ticker WS message into BBO. Discards heartbeats and system messages."""
    if raw.get("channel") != "ticker":
        return None
    if raw.get("type") not in ("update", "snapshot"):
        return None

    try:
        data = raw["data"][0]
        bid = float(data["bid"])
        ask = float(data["ask"])
        bid_qty = float(data["bid_qty"])
        ask_qty = float(data["ask_qty"])
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Kraken: failed to parse BBO: %s — raw: %s", exc, raw)
        return None

    if bid <= 0 or ask <= 0 or bid_qty <= 0 or ask_qty <= 0:
        logger.warning("Kraken: invalid BBO values bid=%s ask=%s bid_qty=%s ask_qty=%s", bid, ask, bid_qty, ask_qty)
        return None

    return BBO(
        exchange=Exchange.KRAKEN,
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        ws_received_at=received_at,
        normalized_at=datetime.now(timezone.utc),
    )


def normalize_coinbase_bbo(raw: dict, received_at: datetime) -> BBO | None:
    # Phase 3
    ...


def normalize_okx_bbo(raw: dict, received_at: datetime) -> BBO | None:
    """Parse OKX v5 tickers WS message into BBO. Discards subscription confirms and errors."""
    if "event" in raw:
        return None
    if raw.get("arg", {}).get("channel") != "tickers":
        return None

    try:
        data = raw["data"][0]
        bid = float(data["bidPx"])
        ask = float(data["askPx"])
        bid_qty = float(data["bidSz"])
        ask_qty = float(data["askSz"])
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("OKX: failed to parse BBO: %s — raw: %s", exc, raw)
        return None

    if bid <= 0 or ask <= 0 or bid_qty <= 0 or ask_qty <= 0:
        logger.warning("OKX: invalid BBO values bid=%s ask=%s bid_qty=%s ask_qty=%s", bid, ask, bid_qty, ask_qty)
        return None

    return BBO(
        exchange=Exchange.OKX,
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        ws_received_at=received_at,
        normalized_at=datetime.now(timezone.utc),
    )
