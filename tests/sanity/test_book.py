from __future__ import annotations

import pytest

from core.book import walk_the_book
from models.market import OrderBookLevel


def _levels(*pairs: tuple[float, float]) -> list[OrderBookLevel]:
    return [OrderBookLevel(price=p, qty=q) for p, q in pairs]


# ── single level ──────────────────────────────────────────────────────────────

def test_walk_single_level_full_fill():
    result = walk_the_book(_levels((70_000.0, 1.0)), target_qty=0.5)
    assert result.filled_qty == pytest.approx(0.5)
    assert result.avg_price == pytest.approx(70_000.0)
    assert result.fill_ratio == pytest.approx(1.0)
    assert result.levels_consumed == 1


# ── walking multiple levels ───────────────────────────────────────────────────

def test_walk_two_levels_weighted_avg_known_answer():
    # 0.3 @ 70_000 + 0.2 @ 70_010 = 21_000 + 14_002 = 35_002; / 0.5 = 70_004.0
    result = walk_the_book(_levels((70_000.0, 0.3), (70_010.0, 0.5)), target_qty=0.5)
    assert result.filled_qty == pytest.approx(0.5)
    assert result.avg_price == pytest.approx(70_004.0)
    assert result.fill_ratio == pytest.approx(1.0)
    assert result.levels_consumed == 2


def test_walk_stops_at_first_level_when_sufficient():
    result = walk_the_book(_levels((70_000.0, 1.0), (70_010.0, 1.0)), target_qty=0.4)
    assert result.levels_consumed == 1
    assert result.avg_price == pytest.approx(70_000.0)


# ── partial fill ──────────────────────────────────────────────────────────────

def test_walk_partial_fill_when_depth_insufficient():
    # total depth 0.5 < target 1.0 → partial
    result = walk_the_book(_levels((70_000.0, 0.3), (70_010.0, 0.2)), target_qty=1.0)
    assert result.filled_qty == pytest.approx(0.5)
    assert result.avg_price == pytest.approx(70_004.0)
    assert result.fill_ratio == pytest.approx(0.5)


def test_walk_empty_book_returns_zero_fill():
    result = walk_the_book([], target_qty=0.5)
    assert result.filled_qty == 0.0
    assert result.avg_price == 0.0
    assert result.fill_ratio == 0.0
    assert result.levels_consumed == 0


# ── input validation ──────────────────────────────────────────────────────────

def test_walk_raises_on_zero_target():
    with pytest.raises(ValueError, match="target_qty must be positive"):
        walk_the_book(_levels((70_000.0, 1.0)), target_qty=0.0)


def test_walk_raises_on_negative_target():
    with pytest.raises(ValueError, match="target_qty must be positive"):
        walk_the_book(_levels((70_000.0, 1.0)), target_qty=-0.5)
