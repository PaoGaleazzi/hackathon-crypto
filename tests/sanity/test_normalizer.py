from __future__ import annotations

from datetime import datetime, timezone

import pytest

from data.normalizer import (
    normalize_binance_bbo,
    normalize_bitstamp_bbo,
    normalize_bybit_bbo,
    normalize_coinbase_bbo,
    normalize_gemini_bbo,
    normalize_kraken_bbo,
)
from models.market import Exchange

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)

# ── Binance ────────────────────────────────────────────────────────────────────

def test_normalize_binance_bbo_parses_fields():
    raw = {"u": 123, "s": "BTCUSDT", "b": "70000.01", "B": "0.521", "a": "70001.50", "A": "1.234"}
    bbo = normalize_binance_bbo(raw, _NOW)
    assert bbo is not None
    assert bbo.exchange == Exchange.BINANCE
    assert bbo.bid == pytest.approx(70000.01)
    assert bbo.ask == pytest.approx(70001.50)
    assert bbo.bid_qty == pytest.approx(0.521)
    assert bbo.ask_qty == pytest.approx(1.234)
    assert bbo.ws_received_at == _NOW
    assert bbo.normalized_at is not None


def test_normalize_binance_bbo_returns_none_on_missing_field():
    raw = {"u": 123, "s": "BTCUSDT", "b": "70000.01"}
    assert normalize_binance_bbo(raw, _NOW) is None


def test_normalize_binance_bbo_returns_none_on_zero_ask():
    raw = {"u": 123, "s": "BTCUSDT", "b": "70000.01", "B": "0.5", "a": "0.0", "A": "1.0"}
    assert normalize_binance_bbo(raw, _NOW) is None


def test_normalize_binance_bbo_returns_none_on_invalid_float():
    raw = {"u": 123, "s": "BTCUSDT", "b": "not_a_number", "B": "0.5", "a": "70001.0", "A": "1.0"}
    assert normalize_binance_bbo(raw, _NOW) is None


# ── Kraken ─────────────────────────────────────────────────────────────────────

def test_normalize_kraken_bbo_parses_update():
    raw = {
        "channel": "ticker",
        "type": "update",
        "data": [{"symbol": "BTC/USD", "bid": 70000.0, "bid_qty": 0.5, "ask": 70002.0, "ask_qty": 0.3}],
    }
    bbo = normalize_kraken_bbo(raw, _NOW)
    assert bbo is not None
    assert bbo.exchange == Exchange.KRAKEN
    assert bbo.bid == pytest.approx(70000.0)
    assert bbo.ask == pytest.approx(70002.0)
    assert bbo.bid_qty == pytest.approx(0.5)
    assert bbo.ask_qty == pytest.approx(0.3)
    assert bbo.ws_received_at == _NOW


def test_normalize_kraken_bbo_parses_snapshot():
    raw = {
        "channel": "ticker",
        "type": "snapshot",
        "data": [{"symbol": "BTC/USD", "bid": 70000.0, "bid_qty": 1.0, "ask": 70005.0, "ask_qty": 2.0}],
    }
    bbo = normalize_kraken_bbo(raw, _NOW)
    assert bbo is not None
    assert bbo.ask == pytest.approx(70005.0)


def test_normalize_kraken_bbo_ignores_heartbeat():
    assert normalize_kraken_bbo({"channel": "heartbeat"}, _NOW) is None


def test_normalize_kraken_bbo_ignores_non_ticker_channel():
    raw = {"channel": "trade", "type": "update", "data": []}
    assert normalize_kraken_bbo(raw, _NOW) is None


def test_normalize_kraken_bbo_ignores_unsupported_type():
    # e.g. internal system message with channel=ticker but unknown type
    raw = {"channel": "ticker", "type": "subscriptions", "data": []}
    assert normalize_kraken_bbo(raw, _NOW) is None


def test_normalize_kraken_bbo_returns_none_on_missing_field():
    raw = {"channel": "ticker", "type": "update", "data": [{"symbol": "BTC/USD", "bid": 70000.0}]}
    assert normalize_kraken_bbo(raw, _NOW) is None


# ── Coinbase ───────────────────────────────────────────────────────────────────

def _coinbase_ticker(
    best_bid: str = "70000.01",
    best_ask: str = "70001.50",
    best_bid_quantity: str = "0.521",
    best_ask_quantity: str = "1.234",
) -> dict:
    return {
        "channel": "ticker",
        "client_id": "",
        "timestamp": "2026-05-29T06:00:00Z",
        "sequence_num": 1,
        "events": [
            {
                "type": "update",
                "tickers": [
                    {
                        "type": "ticker",
                        "product_id": "BTC-USD",
                        "best_bid": best_bid,
                        "best_ask": best_ask,
                        "best_bid_quantity": best_bid_quantity,
                        "best_ask_quantity": best_ask_quantity,
                    }
                ],
            }
        ],
    }


def test_normalize_coinbase_bbo_parses_fields():
    bbo = normalize_coinbase_bbo(_coinbase_ticker(), _NOW)
    assert bbo is not None
    assert bbo.exchange == Exchange.COINBASE
    assert bbo.bid == pytest.approx(70000.01)
    assert bbo.ask == pytest.approx(70001.50)
    assert bbo.bid_qty == pytest.approx(0.521)
    assert bbo.ask_qty == pytest.approx(1.234)
    assert bbo.ws_received_at == _NOW
    assert bbo.normalized_at is not None


def test_normalize_coinbase_bbo_ignores_subscription_confirmation():
    raw = {
        "channel": "subscriptions",
        "client_id": "",
        "timestamp": "2026-05-29T06:00:00Z",
        "sequence_num": 0,
        "events": [{"subscriptions": {"ticker": ["BTC-USD"]}}],
    }
    assert normalize_coinbase_bbo(raw, _NOW) is None


def test_normalize_coinbase_bbo_ignores_non_ticker_channel():
    raw = {"channel": "heartbeats", "events": []}
    assert normalize_coinbase_bbo(raw, _NOW) is None


def test_normalize_coinbase_bbo_returns_none_on_missing_field():
    # tickers list present but required field missing
    raw = {
        "channel": "ticker",
        "events": [{"type": "update", "tickers": [{"product_id": "BTC-USD", "best_bid": "70000.0"}]}],
    }
    assert normalize_coinbase_bbo(raw, _NOW) is None


def test_normalize_coinbase_bbo_returns_none_on_empty_events():
    raw = {"channel": "ticker", "events": []}
    assert normalize_coinbase_bbo(raw, _NOW) is None


def test_normalize_coinbase_bbo_returns_none_on_zero_bid():
    assert normalize_coinbase_bbo(_coinbase_ticker(best_bid="0.0"), _NOW) is None


def test_normalize_coinbase_bbo_returns_none_on_invalid_float():
    assert normalize_coinbase_bbo(_coinbase_ticker(best_ask="not_a_number"), _NOW) is None


# ── Bybit ──────────────────────────────────────────────────────────────────────

def _bybit_ticker(
    bid1_price: str = "70000.01",
    ask1_price: str = "70001.50",
    bid1_size: str = "0.521",
    ask1_size: str = "1.234",
) -> dict:
    return {
        "topic": "tickers.BTCUSDT",
        "type": "snapshot",
        "ts": 1748484000000,
        "data": {
            "symbol": "BTCUSDT",
            "bid1Price": bid1_price,
            "bid1Size": bid1_size,
            "ask1Price": ask1_price,
            "ask1Size": ask1_size,
        },
    }


def test_normalize_bybit_bbo_parses_fields():
    bbo = normalize_bybit_bbo(_bybit_ticker(), _NOW)
    assert bbo is not None
    assert bbo.exchange == Exchange.BYBIT
    assert bbo.bid == pytest.approx(70000.01)
    assert bbo.ask == pytest.approx(70001.50)
    assert bbo.bid_qty == pytest.approx(0.521)
    assert bbo.ask_qty == pytest.approx(1.234)
    assert bbo.ws_received_at == _NOW
    assert bbo.normalized_at is not None


def test_normalize_bybit_bbo_parses_delta_type():
    raw = _bybit_ticker()
    raw["type"] = "delta"
    bbo = normalize_bybit_bbo(raw, _NOW)
    assert bbo is not None
    assert bbo.bid == pytest.approx(70000.01)


def test_normalize_bybit_bbo_ignores_subscription_confirmation():
    raw = {"success": True, "ret_msg": "", "op": "subscribe", "conn_id": "abc"}
    assert normalize_bybit_bbo(raw, _NOW) is None


def test_normalize_bybit_bbo_ignores_wrong_topic():
    raw = _bybit_ticker()
    raw["topic"] = "tickers.ETHUSDT"
    assert normalize_bybit_bbo(raw, _NOW) is None


def test_normalize_bybit_bbo_returns_none_on_missing_field():
    raw = {"topic": "tickers.BTCUSDT", "type": "snapshot", "data": {"bid1Price": "70000.0"}}
    assert normalize_bybit_bbo(raw, _NOW) is None


def test_normalize_bybit_bbo_returns_none_on_zero_ask():
    assert normalize_bybit_bbo(_bybit_ticker(ask1_price="0.0"), _NOW) is None


def test_normalize_bybit_bbo_returns_none_on_invalid_float():
    assert normalize_bybit_bbo(_bybit_ticker(bid1_price="not_a_number"), _NOW) is None


# ── Bitstamp ───────────────────────────────────────────────────────────────────

def _bitstamp_order_book(
    bid_price: str = "70000.01",
    bid_qty: str = "0.521",
    ask_price: str = "70001.50",
    ask_qty: str = "1.234",
) -> dict:
    return {
        "event": "data",
        "channel": "order_book_btcusd",
        "data": {
            "timestamp": "1748484000",
            "microtimestamp": "1748484000000000",
            "bids": [[bid_price, bid_qty], ["69999.00", "2.0"]],
            "asks": [[ask_price, ask_qty], ["70002.00", "0.8"]],
        },
    }


def test_normalize_bitstamp_bbo_parses_fields():
    bbo = normalize_bitstamp_bbo(_bitstamp_order_book(), _NOW)
    assert bbo is not None
    assert bbo.exchange == Exchange.BITSTAMP
    assert bbo.bid == pytest.approx(70000.01)
    assert bbo.ask == pytest.approx(70001.50)
    assert bbo.bid_qty == pytest.approx(0.521)
    assert bbo.ask_qty == pytest.approx(1.234)
    assert bbo.ws_received_at == _NOW
    assert bbo.normalized_at is not None


def test_normalize_bitstamp_bbo_ignores_subscription_succeeded():
    raw = {"event": "bts:subscription_succeeded", "channel": "order_book_btcusd", "data": {}}
    assert normalize_bitstamp_bbo(raw, _NOW) is None


def test_normalize_bitstamp_bbo_ignores_wrong_channel():
    raw = _bitstamp_order_book()
    raw["channel"] = "order_book_ethusd"
    assert normalize_bitstamp_bbo(raw, _NOW) is None


def test_normalize_bitstamp_bbo_returns_none_on_empty_bids():
    raw = _bitstamp_order_book()
    raw["data"]["bids"] = []
    assert normalize_bitstamp_bbo(raw, _NOW) is None


def test_normalize_bitstamp_bbo_returns_none_on_missing_data_key():
    raw = {"event": "data", "channel": "order_book_btcusd"}
    assert normalize_bitstamp_bbo(raw, _NOW) is None


def test_normalize_bitstamp_bbo_returns_none_on_zero_bid():
    assert normalize_bitstamp_bbo(_bitstamp_order_book(bid_price="0.0"), _NOW) is None


def test_normalize_bitstamp_bbo_returns_none_on_invalid_float():
    assert normalize_bitstamp_bbo(_bitstamp_order_book(ask_price="bad"), _NOW) is None


# ── Gemini ─────────────────────────────────────────────────────────────────────
# normalize_gemini_bbo maintains state via mutable bids/asks dicts passed by caller.

def _gemini_update(*events: dict) -> dict:
    return {"type": "update", "eventId": 1, "timestampms": 1748484000000, "events": list(events)}


def _change(side: str, price: str, remaining: str) -> dict:
    return {"type": "change", "side": side, "price": price, "remaining": remaining, "reason": "place"}


def test_normalize_gemini_bbo_returns_bbo_from_book():
    bids: dict[str, float] = {}
    asks: dict[str, float] = {}
    raw = _gemini_update(
        _change("bid", "70000.01", "0.521"),
        _change("ask", "70001.50", "1.234"),
    )
    bbo = normalize_gemini_bbo(raw, bids, asks, _NOW)
    assert bbo is not None
    assert bbo.exchange == Exchange.GEMINI
    assert bbo.bid == pytest.approx(70000.01)
    assert bbo.ask == pytest.approx(70001.50)
    assert bbo.bid_qty == pytest.approx(0.521)
    assert bbo.ask_qty == pytest.approx(1.234)
    assert bbo.ws_received_at == _NOW
    assert bbo.normalized_at is not None


def test_normalize_gemini_bbo_selects_best_bid_and_ask():
    # best bid = highest price, best ask = lowest price
    bids = {"69999.00": 1.0, "70000.00": 0.5}
    asks = {"70002.00": 0.8, "70001.00": 1.5}
    raw = _gemini_update()  # no new events — just recompute from existing book
    bbo = normalize_gemini_bbo(raw, bids, asks, _NOW)
    assert bbo is not None
    assert bbo.bid == pytest.approx(70000.00)
    assert bbo.ask == pytest.approx(70001.00)


def test_normalize_gemini_bbo_removes_level_when_remaining_zero():
    bids: dict[str, float] = {"70000.00": 0.5}
    asks: dict[str, float] = {"70001.00": 1.0}
    raw = _gemini_update(_change("bid", "70000.00", "0"))
    bbo = normalize_gemini_bbo(raw, bids, asks, _NOW)
    assert bbo is None          # bids now empty
    assert "70000.00" not in bids


def test_normalize_gemini_bbo_returns_none_when_book_empty_on_connect():
    bids: dict[str, float] = {}
    asks: dict[str, float] = {}
    raw = _gemini_update()
    assert normalize_gemini_bbo(raw, bids, asks, _NOW) is None


def test_normalize_gemini_bbo_ignores_heartbeat():
    bids: dict[str, float] = {}
    asks: dict[str, float] = {}
    raw = {"type": "heartbeat", "timestampms": 1748484000000, "sequence": 1}
    assert normalize_gemini_bbo(raw, bids, asks, _NOW) is None


def test_normalize_gemini_bbo_ignores_non_change_events():
    bids: dict[str, float] = {}
    asks: dict[str, float] = {}
    raw = _gemini_update({"type": "trade", "side": "buy", "price": "70000", "amount": "0.1"})
    assert normalize_gemini_bbo(raw, bids, asks, _NOW) is None


def test_normalize_gemini_bbo_accumulates_across_calls():
    bids: dict[str, float] = {}
    asks: dict[str, float] = {}
    normalize_gemini_bbo(_gemini_update(_change("bid", "70000.00", "0.5")), bids, asks, _NOW)
    bbo = normalize_gemini_bbo(_gemini_update(_change("ask", "70001.00", "1.0")), bids, asks, _NOW)
    assert bbo is not None
    assert bbo.bid == pytest.approx(70000.00)
    assert bbo.ask == pytest.approx(70001.00)
