from __future__ import annotations

import math
from datetime import datetime, timezone

import pytest

from core.microprice import (
    MicropriceEstimator,
    MicropriceSnapshot,
    microprice,
    microprice_adjustment,
)
from models.market import BBO, Exchange


# ── microprice: known-answer cases ────────────────────────────────────────────

def test_microprice_balanced_book_equals_mid():
    # imbalance 50/50 → micro == mid
    bid, ask = 100.0, 102.0
    result = microprice(bid, ask, bid_size=10, ask_size=10)
    assert result == pytest.approx((bid + ask) / 2.0)


def test_microprice_all_volume_on_bid_tends_to_ask():
    # imbalance → 1 → micro → ask (buying pressure pushes fair price up)
    result = microprice(bid=100.0, ask=102.0, bid_size=1e9, ask_size=1.0)
    assert result == pytest.approx(102.0, rel=1e-6)


def test_microprice_all_volume_on_ask_tends_to_bid():
    # imbalance → 0 → micro → bid (selling pressure pushes fair price down)
    result = microprice(bid=100.0, ask=102.0, bid_size=1.0, ask_size=1e9)
    assert result == pytest.approx(100.0, rel=1e-6)


def test_microprice_exact_75_25_imbalance():
    # imbalance = 30/40 = 0.75
    # micro = 102*0.75 + 100*0.25 = 76.5 + 25 = 101.5
    result = microprice(bid=100.0, ask=102.0, bid_size=30, ask_size=10)
    assert result == pytest.approx(101.5)


def test_microprice_exact_25_75_imbalance():
    # imbalance = 10/40 = 0.25
    # micro = 102*0.25 + 100*0.75 = 25.5 + 75 = 100.5
    result = microprice(bid=100.0, ask=102.0, bid_size=10, ask_size=30)
    assert result == pytest.approx(100.5)


def test_microprice_bounded_between_bid_and_ask():
    # Convex combination → always within [bid, ask]
    result = microprice(bid=100.0, ask=102.0, bid_size=7, ask_size=3)
    assert 100.0 <= result <= 102.0


def test_microprice_raises_on_zero_bid_size():
    with pytest.raises(ValueError):
        microprice(bid=100.0, ask=102.0, bid_size=0, ask_size=10)


def test_microprice_raises_on_negative_ask_size():
    with pytest.raises(ValueError):
        microprice(bid=100.0, ask=102.0, bid_size=10, ask_size=-5)


# ── microprice_adjustment ─────────────────────────────────────────────────────

def test_adjustment_zero_for_balanced_book():
    assert microprice_adjustment(100.0, 102.0, 10, 10) == pytest.approx(0.0)


def test_adjustment_positive_for_bid_pressure():
    # micro=101.5, mid=101 → +0.5
    assert microprice_adjustment(100.0, 102.0, 30, 10) == pytest.approx(0.5)


def test_adjustment_negative_for_ask_pressure():
    # micro=100.5, mid=101 → -0.5
    assert microprice_adjustment(100.0, 102.0, 10, 30) == pytest.approx(-0.5)


# ── MicropriceEstimator ───────────────────────────────────────────────────────

def test_estimator_current_returns_none_before_update():
    est = MicropriceEstimator()
    assert est.current(Exchange.BINANCE) is None


def test_estimator_update_returns_correct_snapshot():
    est = MicropriceEstimator()
    snap = est.update(Exchange.BINANCE, bid=100.0, ask=102.0, bid_size=30, ask_size=10)
    assert isinstance(snap, MicropriceSnapshot)
    assert snap.micro == pytest.approx(101.5)
    assert snap.mid == pytest.approx(101.0)
    assert snap.adjustment == pytest.approx(0.5)
    assert snap.imbalance == pytest.approx(0.75)


def test_estimator_current_reflects_latest_update():
    est = MicropriceEstimator()
    est.update(Exchange.KRAKEN, bid=100.0, ask=102.0, bid_size=10, ask_size=10)
    est.update(Exchange.KRAKEN, bid=100.0, ask=102.0, bid_size=30, ask_size=10)
    current = est.current(Exchange.KRAKEN)
    assert current is not None
    assert current.micro == pytest.approx(101.5)


def test_estimator_keys_are_isolated_by_exchange():
    est = MicropriceEstimator()
    est.update(Exchange.BINANCE, bid=100.0, ask=102.0, bid_size=30, ask_size=10)
    est.update(Exchange.KRAKEN, bid=100.0, ask=102.0, bid_size=10, ask_size=30)
    assert est.current(Exchange.BINANCE).micro == pytest.approx(101.5)
    assert est.current(Exchange.KRAKEN).micro == pytest.approx(100.5)


def test_estimator_keys_are_isolated_by_symbol():
    est = MicropriceEstimator()
    est.update(Exchange.BINANCE, 100.0, 102.0, 30, 10, symbol="BTC-USD")
    est.update(Exchange.BINANCE, 100.0, 102.0, 10, 30, symbol="ETH-USD")
    assert est.current(Exchange.BINANCE, "BTC-USD").micro == pytest.approx(101.5)
    assert est.current(Exchange.BINANCE, "ETH-USD").micro == pytest.approx(100.5)


def test_estimator_window_is_bounded():
    est = MicropriceEstimator(history_len=3)
    for _ in range(5):
        est.update(Exchange.OKX, bid=100.0, ask=102.0, bid_size=10, ask_size=10)
    window = est._history[(Exchange.OKX, "BTC-USD")]
    assert len(window) == 3


def test_estimator_trend_is_nan_with_single_point():
    est = MicropriceEstimator()
    est.update(Exchange.BINANCE, bid=100.0, ask=102.0, bid_size=10, ask_size=10)
    assert math.isnan(est.trend(Exchange.BINANCE))


def test_estimator_trend_is_nan_for_unknown_key():
    est = MicropriceEstimator()
    assert math.isnan(est.trend(Exchange.GEMINI))


def test_estimator_trend_positive_for_rising_micro():
    # micros: 100, 101, 102 → trend = (102-100)/2 = 1.0
    est = MicropriceEstimator()
    est.update(Exchange.BINANCE, bid=100.0, ask=100.0, bid_size=10, ask_size=10)  # micro=100
    est.update(Exchange.BINANCE, bid=101.0, ask=101.0, bid_size=10, ask_size=10)  # micro=101
    est.update(Exchange.BINANCE, bid=102.0, ask=102.0, bid_size=10, ask_size=10)  # micro=102
    assert est.trend(Exchange.BINANCE) == pytest.approx(1.0)


def test_estimator_trend_negative_for_falling_micro():
    est = MicropriceEstimator()
    est.update(Exchange.BINANCE, bid=102.0, ask=102.0, bid_size=10, ask_size=10)
    est.update(Exchange.BINANCE, bid=100.0, ask=100.0, bid_size=10, ask_size=10)
    assert est.trend(Exchange.BINANCE) == pytest.approx(-2.0)


def test_estimator_update_from_bbo_matches_update():
    est = MicropriceEstimator()
    bbo = BBO(
        exchange=Exchange.BYBIT,
        bid=100.0,
        ask=102.0,
        bid_qty=30.0,
        ask_qty=10.0,
        ws_received_at=datetime.now(timezone.utc),
    )
    snap = est.update_from_bbo(bbo)
    assert snap.micro == pytest.approx(101.5)
    assert snap.imbalance == pytest.approx(0.75)


def test_estimator_rejects_history_len_below_two():
    with pytest.raises(ValueError):
        MicropriceEstimator(history_len=1)
