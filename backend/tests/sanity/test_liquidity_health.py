from __future__ import annotations

import pytest

from core.liquidity_health import (
    FRAGMENTATION_THRESHOLD,
    FragmentationResult,
    LiquidityHealthMonitor,
    LiquidityStatus,
    compute_fragmentation_score,
)
from models.market import Exchange, OrderBookLevel


# ── helpers ───────────────────────────────────────────────────────────────────

def make_levels(prices: list[float], qtys: list[float]) -> list[OrderBookLevel]:
    return [OrderBookLevel(price=p, qty=q) for p, q in zip(prices, qtys)]


# ── compute_fragmentation_score ───────────────────────────────────────────────

def test_compute_fragmentation_score_healthy_known_answer():
    # 4 levels, uniform qty=5, price gaps of $1, reference_price=1000
    # rel_gap = 1/1000 = 0.001 each
    # weighted_gap_sum = 0.001/5 + 0.001/5 + 0.001/5 = 3 × 2e-4 = 6e-4
    # total_depth = 4 × 5 = 20
    # score = 6e-4 / 20 = 3e-5
    levels = make_levels([1000, 1001, 1002, 1003], [5, 5, 5, 5])
    result = compute_fragmentation_score(levels)
    assert result == pytest.approx(3e-5, rel=1e-6)


def test_compute_fragmentation_score_fragmented_known_answer():
    # 4 levels, sparse qty=0.1, price gaps of $10, reference_price=1000
    # rel_gap = 10/1000 = 0.01 each
    # weighted_gap_sum = 0.01/0.1 + 0.01/0.1 + 0.01/0.1 = 3 × 0.1 = 0.3
    # total_depth = 4 × 0.1 = 0.4
    # score = 0.3 / 0.4 = 0.75
    levels = make_levels([1000, 1010, 1020, 1030], [0.1, 0.1, 0.1, 0.1])
    result = compute_fragmentation_score(levels)
    assert result == pytest.approx(0.75, rel=1e-6)


def test_compute_fragmentation_score_healthy_less_than_fragmented():
    healthy = make_levels([1000, 1001, 1002, 1003], [5, 5, 5, 5])
    fragmented = make_levels([1000, 1010, 1020, 1030], [0.1, 0.1, 0.1, 0.1])
    assert compute_fragmentation_score(healthy) < compute_fragmentation_score(fragmented)


def test_compute_fragmentation_score_single_level_returns_zero():
    # One level → no gaps to measure
    levels = make_levels([100.0], [10.0])
    assert compute_fragmentation_score(levels) == 0.0


def test_compute_fragmentation_score_empty_returns_zero():
    assert compute_fragmentation_score([]) == 0.0


def test_compute_fragmentation_score_top_n_truncation():
    # top_n=2 uses only first 2 levels, ignoring the large gap at level 3
    levels = make_levels([100, 100.1, 200.0], [10, 10, 10])
    score_top2 = compute_fragmentation_score(levels, top_n=2)
    score_all = compute_fragmentation_score(levels, top_n=3)
    # top_n=2: only 1 gap of 0.1 → score is small
    # all: includes gap of ~100 → score is much larger
    assert score_top2 < score_all


def test_compute_fragmentation_score_increases_with_gap_size():
    # Wider gaps → higher score, holding depth constant
    narrow = make_levels([1000, 1001, 1002], [5, 5, 5])
    wide = make_levels([1000, 1010, 1020], [5, 5, 5])
    assert compute_fragmentation_score(narrow) < compute_fragmentation_score(wide)


def test_compute_fragmentation_score_decreases_with_depth():
    # More depth per level → lower score, holding gaps constant
    thin = make_levels([1000, 1010, 1020], [0.1, 0.1, 0.1])
    deep = make_levels([1000, 1010, 1020], [10.0, 10.0, 10.0])
    assert compute_fragmentation_score(deep) < compute_fragmentation_score(thin)


# ── LiquidityHealthMonitor ────────────────────────────────────────────────────

def test_monitor_marks_healthy_book_as_healthy():
    monitor = LiquidityHealthMonitor(threshold=FRAGMENTATION_THRESHOLD)
    levels = make_levels([1000, 1001, 1002, 1003], [5, 5, 5, 5])
    result = monitor.update(Exchange.BINANCE, levels)
    assert result.status == LiquidityStatus.HEALTHY
    assert result.score < FRAGMENTATION_THRESHOLD


def test_monitor_marks_fragmented_book_as_degraded():
    monitor = LiquidityHealthMonitor(threshold=FRAGMENTATION_THRESHOLD)
    levels = make_levels([1000, 1010, 1020, 1030], [0.1, 0.1, 0.1, 0.1])
    result = monitor.update(Exchange.KRAKEN, levels)
    assert result.status == LiquidityStatus.DEGRADED
    assert result.score > FRAGMENTATION_THRESHOLD


def test_monitor_is_healthy_returns_true_for_unknown_exchange():
    # No data → optimistic default, don't block the pipeline
    monitor = LiquidityHealthMonitor()
    assert monitor.is_healthy(Exchange.OKX) is True


def test_monitor_is_healthy_reflects_update():
    monitor = LiquidityHealthMonitor(threshold=FRAGMENTATION_THRESHOLD)
    fragmented = make_levels([1000, 1010, 1020], [0.1, 0.1, 0.1])
    monitor.update(Exchange.COINBASE, fragmented)
    assert monitor.is_healthy(Exchange.COINBASE) is False


def test_monitor_get_all_returns_all_updated_exchanges():
    monitor = LiquidityHealthMonitor()
    monitor.update(Exchange.BINANCE, make_levels([1000, 1001], [5, 5]))
    monitor.update(Exchange.KRAKEN, make_levels([1000, 1001], [5, 5]))
    state = monitor.get_all()
    assert Exchange.BINANCE in state
    assert Exchange.KRAKEN in state


def test_monitor_as_dict_structure():
    monitor = LiquidityHealthMonitor()
    levels = make_levels([1000, 1001, 1002], [5, 5, 5])
    monitor.update(Exchange.BINANCE, levels)
    d = monitor.as_dict()
    assert "binance" in d
    entry = d["binance"]
    assert "score" in entry
    assert "status" in entry
    assert "level_count" in entry
    assert "computed_at" in entry


def test_monitor_level_count_capped_at_top_n():
    monitor = LiquidityHealthMonitor()
    levels = make_levels(list(range(1000, 1020)), [5.0] * 20)
    result = monitor.update(Exchange.BINANCE, levels, top_n=10)
    assert result.level_count == 10
