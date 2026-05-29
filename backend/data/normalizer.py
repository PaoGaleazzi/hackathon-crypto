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
    """Parse Coinbase Advanced Trade ticker WS message into BBO.

    Ticker updates arrive as:
      {"channel": "ticker", "events": [{"tickers": [{
        "product_id": "BTC-USD", "best_bid": "...", "best_ask": "...",
        "best_bid_size": "...", "best_ask_size": "..."
      }]}]}
    Subscription confirmations have channel="subscriptions" — discarded.
    """
    if raw.get("channel") != "ticker":
        return None

    try:
        ticker = raw["events"][0]["tickers"][0]
        bid = float(ticker["best_bid"])
        ask = float(ticker["best_ask"])
        bid_qty = float(ticker["best_bid_size"])
        ask_qty = float(ticker["best_ask_size"])
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Coinbase: failed to parse BBO: %s — raw: %s", exc, raw)
        return None

    if bid <= 0 or ask <= 0 or bid_qty <= 0 or ask_qty <= 0:
        logger.warning("Coinbase: invalid BBO values bid=%s ask=%s bid_qty=%s ask_qty=%s", bid, ask, bid_qty, ask_qty)
        return None

    return BBO(
        exchange=Exchange.COINBASE,
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        ws_received_at=received_at,
        normalized_at=datetime.now(timezone.utc),
    )


def normalize_gemini_bbo(
    raw: dict,
    bids: dict[str, float],
    asks: dict[str, float],
    received_at: datetime,
) -> BBO | None:
    """Apply a Gemini BTCUSD delta update to the in-memory book, return current BBO.

    Delta updates arrive as:
      {"type": "update", "events": [
        {"type": "change", "side": "bid"/"ask", "price": "...", "remaining": "..."},
        ...
      ]}
    remaining == "0" removes that price level. bids/asks are mutated in place.
    Returns BBO from current top-of-book after applying all deltas, or None when
    the book is empty on either side (common at startup before the snapshot completes).
    """
    if raw.get("type") != "update":
        return None

    for event in raw.get("events", []):
        if event.get("type") != "change":
            continue
        side = event.get("side")
        price_str = event.get("price")
        remaining_str = event.get("remaining")
        if side not in ("bid", "ask") or price_str is None or remaining_str is None:
            continue
        try:
            qty = float(remaining_str)
        except ValueError:
            continue
        book = bids if side == "bid" else asks
        if qty <= 0:
            book.pop(price_str, None)
        else:
            book[price_str] = qty

    if not bids or not asks:
        return None

    try:
        best_bid_str = max(bids, key=lambda p: float(p))
        best_ask_str = min(asks, key=lambda p: float(p))
        bid = float(best_bid_str)
        ask = float(best_ask_str)
        bid_qty = bids[best_bid_str]
        ask_qty = asks[best_ask_str]
    except (ValueError, KeyError) as exc:
        logger.warning("Gemini: failed to compute BBO from book: %s", exc)
        return None

    if bid <= 0 or ask <= 0 or bid_qty <= 0 or ask_qty <= 0:
        logger.warning("Gemini: invalid BBO values bid=%s ask=%s bid_qty=%s ask_qty=%s", bid, ask, bid_qty, ask_qty)
        return None

    return BBO(
        exchange=Exchange.GEMINI,
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        ws_received_at=received_at,
        normalized_at=datetime.now(timezone.utc),
    )


def normalize_bitstamp_bbo(raw: dict, received_at: datetime) -> BBO | None:
    """Parse Bitstamp order_book_btcusd WS message into BBO.

    Data updates arrive as:
      {"event": "data", "channel": "order_book_btcusd",
       "data": {"bids": [["70000.01", "0.521"], ...], "asks": [["70001.50", "1.234"], ...]}}
    bids and asks are sorted best-first; we take index 0 for the BBO.
    Subscription confirmations have event="bts:subscription_succeeded" — discarded.
    """
    if raw.get("event") != "data":
        return None
    if raw.get("channel") != "order_book_btcusd":
        return None

    try:
        data = raw["data"]
        bid = float(data["bids"][0][0])
        bid_qty = float(data["bids"][0][1])
        ask = float(data["asks"][0][0])
        ask_qty = float(data["asks"][0][1])
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Bitstamp: failed to parse BBO: %s — raw: %s", exc, raw)
        return None

    if bid <= 0 or ask <= 0 or bid_qty <= 0 or ask_qty <= 0:
        logger.warning("Bitstamp: invalid BBO values bid=%s ask=%s bid_qty=%s ask_qty=%s", bid, ask, bid_qty, ask_qty)
        return None

    return BBO(
        exchange=Exchange.BITSTAMP,
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        ws_received_at=received_at,
        normalized_at=datetime.now(timezone.utc),
    )


def normalize_bybit_bbo(raw: dict, received_at: datetime) -> BBO | None:
    """Parse Bybit v5 spot tickers WS message into BBO.

    Ticker updates arrive as:
      {"topic": "tickers.BTCUSDT", "type": "snapshot"|"delta",
       "data": {"bid1Price": "...", "bid1Size": "...", "ask1Price": "...", "ask1Size": "..."}}
    Subscription confirmations have op="subscribe" — discarded.
    """
    if raw.get("topic") != "tickers.BTCUSDT":
        return None

    try:
        data = raw["data"]
        bid = float(data["bid1Price"])
        ask = float(data["ask1Price"])
        bid_qty = float(data["bid1Size"])
        ask_qty = float(data["ask1Size"])
    except (KeyError, ValueError) as exc:
        logger.warning("Bybit: failed to parse BBO: %s — raw: %s", exc, raw)
        return None

    if bid <= 0 or ask <= 0 or bid_qty <= 0 or ask_qty <= 0:
        logger.warning("Bybit: invalid BBO values bid=%s ask=%s bid_qty=%s ask_qty=%s", bid, ask, bid_qty, ask_qty)
        return None

    return BBO(
        exchange=Exchange.BYBIT,
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        ws_received_at=received_at,
        normalized_at=datetime.now(timezone.utc),
    )


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
