from __future__ import annotations

from datetime import datetime, timezone

import pytest

from data.normalizer import normalize_binance_bbo, normalize_kraken_bbo
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
