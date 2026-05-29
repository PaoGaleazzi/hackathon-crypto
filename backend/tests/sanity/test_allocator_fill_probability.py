from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.allocator import build_allocation_inputs
from core.fill_probability import expected_profit
from models.market import Exchange, Opportunity
from models.trade import WalletBalance


def _make_opportunity(detected_at: datetime, net_spread: float = 100.0) -> Opportunity:
    return Opportunity(
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        buy_ask=100_000.0,
        sell_bid=100_200.0,
        gross_spread=200.0,
        net_spread=net_spread,
        score=0.0,
        detected_at=detected_at,
        available_qty=1.0,
        optimal_qty=1.0,
    )


def _wallets() -> dict[Exchange, WalletBalance]:
    updated = datetime(2026, 5, 29, tzinfo=timezone.utc)
    return {
        Exchange.BINANCE: WalletBalance(
            exchange=Exchange.BINANCE, usdt=1_000_000.0, btc=10.0, updated_at=updated
        ),
        Exchange.KRAKEN: WalletBalance(
            exchange=Exchange.KRAKEN, usdt=1_000_000.0, btc=10.0, updated_at=updated
        ),
    }


def test_spatial_return_equals_expected_profit_per_unit_capital():
    # r_i must be E[profit](opp, now) / capital_basis, NOT net_spread / capital_basis.
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    opp = _make_opportunity(now - timedelta(milliseconds=50.0), net_spread=100.0)
    capital_basis = opp.available_qty * opp.buy_ask

    inputs = build_allocation_inputs([opp], [], _wallets(), now=now, tau_ms=50.0)

    expected_r = expected_profit(opp, now, tau_ms=50.0) / capital_basis
    assert inputs.expected_returns[0] == pytest.approx(expected_r, rel=1e-9)


def test_fresh_spatial_gets_higher_return_than_stale_same_spread():
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    fresh = _make_opportunity(now - timedelta(milliseconds=5.0), net_spread=100.0)
    stale = _make_opportunity(now - timedelta(milliseconds=300.0), net_spread=100.0)

    inputs = build_allocation_inputs([fresh, stale], [], _wallets(), now=now)

    assert inputs.expected_returns[0] > inputs.expected_returns[1]


def test_stale_spatial_yields_negative_return_when_penalty_dominates():
    # An old opportunity's E[profit] goes negative -> r_i < 0, so the QP (maximize
    # rᵀx, x>=0) allocates zero capital to it.
    now = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)
    stale = _make_opportunity(now - timedelta(milliseconds=500.0), net_spread=100.0)

    inputs = build_allocation_inputs([stale], [], _wallets(), now=now)

    assert inputs.expected_returns[0] < 0.0
