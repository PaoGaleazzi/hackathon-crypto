from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from core.stat_arb import (
    DEFAULT_ENTRY_THRESHOLD,
    SignalDirection,
    SpreadStats,
    StatArbDetector,
    compute_zscore,
    estimate_half_life,
    estimate_ou_parameters,
    rolling_mean_std,
)
from models.market import BBO, Exchange

_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)


def _ts(i: int) -> datetime:
    return _NOW + timedelta(seconds=i)


def _bbo(exchange: Exchange, mid: float, received_at: datetime) -> BBO:
    return BBO(
        exchange=exchange,
        bid=mid - 0.5,
        ask=mid + 0.5,
        bid_qty=1.0,
        ask_qty=1.0,
        ws_received_at=received_at,
    )


def _feed(detector: StatArbDetector, spreads: list[float], base: float = 70_000.0):
    """Feed binance-vs-kraken spreads (mid_binance - mid_kraken = s). Returns
    the list of signal-lists, one per update call."""
    out = []
    for i, s in enumerate(spreads):
        bbos = {
            Exchange.BINANCE: _bbo(Exchange.BINANCE, base + s, _ts(i)),
            Exchange.KRAKEN: _bbo(Exchange.KRAKEN, base, _ts(i)),
        }
        out.append(detector.update(bbos, now=_ts(i)))
    return out


# ── compute_zscore ──────────────────────────────────────────────────────────────

def test_compute_zscore_known_answer():
    # value=5, mean=3, std=sqrt(2.5)=1.58113883 → z = 2/1.58113883 = 1.26491106
    z = compute_zscore(5.0, 3.0, np.sqrt(2.5))
    assert z == pytest.approx(1.2649110640673518, rel=1e-9)


def test_compute_zscore_returns_nan_for_zero_std():
    assert np.isnan(compute_zscore(5.0, 3.0, 0.0))


# ── rolling_mean_std ──────────────────────────────────────────────────────────────

def test_rolling_mean_std_known_answer():
    # [1,2,3,4,5]: mean=3, sample var = 10/4 = 2.5, std = 1.58113883
    mean, std = rolling_mean_std(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert mean == pytest.approx(3.0)
    assert std == pytest.approx(1.5811388300841898, rel=1e-9)


def test_rolling_mean_std_single_element_has_zero_std():
    mean, std = rolling_mean_std(np.array([42.0]))
    assert mean == pytest.approx(42.0)
    assert std == 0.0


def test_rolling_mean_std_empty_raises():
    with pytest.raises(ValueError):
        rolling_mean_std(np.array([]))


# ── estimate_half_life ──────────────────────────────────────────────────────────

def test_half_life_known_answer_geometric_reversion():
    # X_t = 0.5^t → ΔX_t = -0.5·X_{t-1} exactly → slope b = -0.5
    # half_life = -ln(2)/b = ln(2)/0.5 = 1.3862943611
    series = np.array([1.0, 0.5, 0.25, 0.125, 0.0625])
    hl = estimate_half_life(series)
    assert hl == pytest.approx(1.3862943611198906, rel=1e-9)


def test_half_life_inf_for_random_walk_with_drift():
    # [1,2,3,4,5]: ΔX constant (=1), independent of lag → slope 0 → no reversion
    hl = estimate_half_life(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert hl == np.inf


def test_half_life_inf_for_too_short_series():
    assert estimate_half_life(np.array([1.0, 2.0])) == np.inf


def test_half_life_inf_for_flat_series():
    # No variation in the lag → no reversion information
    assert estimate_half_life(np.array([5.0, 5.0, 5.0, 5.0])) == np.inf


# ── estimate_ou_parameters ──────────────────────────────────────────────────────

def test_estimate_ou_parameters_known_answer():
    stats_ = estimate_ou_parameters(np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    assert stats_.mean == pytest.approx(3.0)
    assert stats_.std == pytest.approx(1.5811388300841898, rel=1e-9)
    # z-score of last point (5): (5-3)/1.58113883 = 1.26491106
    assert stats_.zscore == pytest.approx(1.2649110640673518, rel=1e-9)
    assert stats_.half_life == np.inf  # monotonic = no reversion
    assert stats_.n_samples == 5


def test_estimate_ou_parameters_empty_raises():
    with pytest.raises(ValueError):
        estimate_ou_parameters(np.array([]))


# ── StatArbDetector ──────────────────────────────────────────────────────────────

def test_detector_emits_signal_on_positive_divergence():
    # 30 small alternating spreads (mean≈0, std≈1) then a +10 outlier.
    # z of the outlier ≈ 4.7 > 2 → signal, spread positive → SHORT_A.
    detector = StatArbDetector()
    spreads = [1.0, -1.0] * 15 + [10.0]
    out = _feed(detector, spreads)

    assert len(out[-1]) == 1
    sig = out[-1][0]
    assert sig.exchange_a == Exchange.BINANCE  # canonical: "binance" < "kraken"
    assert sig.exchange_b == Exchange.KRAKEN
    assert sig.spread == pytest.approx(10.0)
    assert abs(sig.zscore) > DEFAULT_ENTRY_THRESHOLD
    assert sig.direction == SignalDirection.CONVERGE_SHORT_A


def test_detector_emits_long_a_on_negative_divergence():
    detector = StatArbDetector()
    spreads = [1.0, -1.0] * 15 + [-10.0]
    out = _feed(detector, spreads)

    assert len(out[-1]) == 1
    sig = out[-1][0]
    assert sig.zscore < -DEFAULT_ENTRY_THRESHOLD
    assert sig.direction == SignalDirection.CONVERGE_LONG_A


def test_detector_no_signal_when_spread_stable():
    # Alternating ±1 spreads never reach |z| > 2.
    detector = StatArbDetector()
    spreads = [1.0, -1.0] * 20
    out = _feed(detector, spreads)
    assert all(len(s) == 0 for s in out)


def test_detector_silent_below_min_samples():
    # min_samples=30; feeding only 20 ticks → no stats, no signals.
    detector = StatArbDetector(min_samples=30)
    spreads = [10.0, -10.0] * 10  # 20 ticks, wild but too few
    out = _feed(detector, spreads)
    assert all(len(s) == 0 for s in out)
    assert detector.get_stats(Exchange.BINANCE, Exchange.KRAKEN) is None


def test_get_stats_is_pair_order_invariant():
    detector = StatArbDetector()
    _feed(detector, [1.0, -1.0] * 20)
    s1 = detector.get_stats(Exchange.BINANCE, Exchange.KRAKEN)
    s2 = detector.get_stats(Exchange.KRAKEN, Exchange.BINANCE)
    assert isinstance(s1, SpreadStats)
    assert s1 == s2


def test_detector_rejects_invalid_window_size():
    with pytest.raises(ValueError):
        StatArbDetector(window_size=1)


def test_detector_rejects_invalid_entry_threshold():
    with pytest.raises(ValueError):
        StatArbDetector(entry_threshold=0.0)
