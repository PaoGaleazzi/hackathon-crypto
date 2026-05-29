from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

from core.allocator import build_allocation_inputs, optimize_allocation
from core.triangular import detect_triangular
from models.market import BBO, Exchange, Opportunity
from models.trade import WalletBalance

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)


def _spatial_opp(net_spread: float = 100.0) -> Opportunity:
    # available_qty=1 BTC @ ask 100_000 → capital basis 100_000 USDT.
    return Opportunity(
        buy_exchange=Exchange.KRAKEN,
        sell_exchange=Exchange.COINBASE,
        buy_ask=100_000.0,
        sell_bid=100_150.0,
        gross_spread=150.0,
        net_spread=net_spread,
        score=0.0015,
        detected_at=_NOW,
        available_qty=1.0,
        optimal_qty=1.0,
    )


def _wallets(usdt: float = 10_000.0) -> dict[Exchange, WalletBalance]:
    return {
        ex: WalletBalance(exchange=ex, usdt=usdt, btc=0.5, updated_at=_NOW)
        for ex in Exchange
    }


def _bbo(exchange: Exchange, bid: float, ask: float) -> BBO:
    return BBO(exchange=exchange, bid=bid, ask=ask, bid_qty=1.0, ask_qty=1.0, ws_received_at=_NOW)


def test_optimize_allocation_fills_to_wallet_cap_when_risk_neutral():
    # λ=0, positive return → push to the binding wallet cap (500 < max 1000).
    result = optimize_allocation(
        expected_returns=np.array([0.01]),
        cov_matrix=np.array([[0.0]]),
        wallet_caps={"A": 500.0},
        wallet_of=["A"],
        max_per_opp=np.array([1000.0]),
        risk_aversion=0.0,
    )
    assert result.allocations[0] == pytest.approx(500.0, rel=1e-3)
    assert result.expected_profit == pytest.approx(5.0, rel=1e-3)  # 0.01 * 500


def test_optimize_allocation_returns_interior_meanvariance_optimum():
    # Unconstrained concave optimum: x* = r / (2λσ²) = 0.02 / (2·1·0.0001) = 100,
    # which sits strictly inside [0, 1000] and below the wallet cap.
    result = optimize_allocation(
        expected_returns=np.array([0.02]),
        cov_matrix=np.array([[0.0001]]),
        wallet_caps={"A": 1000.0},
        wallet_of=["A"],
        max_per_opp=np.array([1000.0]),
        risk_aversion=1.0,
    )
    assert result.allocations[0] == pytest.approx(100.0, rel=1e-2)


def test_optimize_allocation_skips_negative_expected_return():
    result = optimize_allocation(
        expected_returns=np.array([-0.01]),
        cov_matrix=np.array([[0.0001]]),
        wallet_caps={"A": 1000.0},
        wallet_of=["A"],
        max_per_opp=np.array([1000.0]),
        risk_aversion=1.0,
    )
    assert result.allocations[0] == pytest.approx(0.0, abs=1e-4)


def test_optimize_allocation_concentrates_shared_wallet_on_best_return():
    # Both draw on wallet A (cap 600), λ=0 → all capital to the higher return.
    result = optimize_allocation(
        expected_returns=np.array([0.02, 0.01]),
        cov_matrix=np.zeros((2, 2)),
        wallet_caps={"A": 600.0},
        wallet_of=["A", "A"],
        max_per_opp=np.array([1000.0, 1000.0]),
        risk_aversion=0.0,
    )
    assert result.allocations[0] == pytest.approx(600.0, rel=1e-3)
    assert result.allocations[1] == pytest.approx(0.0, abs=1e-3)
    assert result.expected_profit == pytest.approx(12.0, rel=1e-3)  # 0.02 * 600


def test_optimize_allocation_fills_independent_wallets_to_their_caps():
    result = optimize_allocation(
        expected_returns=np.array([0.01, 0.02]),
        cov_matrix=np.zeros((2, 2)),
        wallet_caps={"A": 500.0, "B": 300.0},
        wallet_of=["A", "B"],
        max_per_opp=np.array([1000.0, 1000.0]),
        risk_aversion=0.0,
    )
    assert result.allocations[0] == pytest.approx(500.0, rel=1e-3)
    assert result.allocations[1] == pytest.approx(300.0, rel=1e-3)
    assert result.expected_profit == pytest.approx(11.0, rel=1e-3)  # 5 + 6


def test_optimize_allocation_caps_at_per_opportunity_limit():
    # Interior optimum is enormous; max_per_opp=50 binds before the wallet.
    result = optimize_allocation(
        expected_returns=np.array([0.05]),
        cov_matrix=np.array([[1e-8]]),
        wallet_caps={"A": 1000.0},
        wallet_of=["A"],
        max_per_opp=np.array([50.0]),
        risk_aversion=1.0,
    )
    assert result.allocations[0] == pytest.approx(50.0, rel=1e-3)


def test_optimize_allocation_handles_empty_opportunity_set():
    result = optimize_allocation(
        expected_returns=np.array([]),
        cov_matrix=np.zeros((0, 0)),
        wallet_caps={},
        wallet_of=[],
        max_per_opp=np.array([]),
    )
    assert result.allocations.shape == (0,)
    assert result.expected_profit == 0.0


def test_optimize_allocation_raises_on_negative_risk_aversion():
    with pytest.raises(ValueError, match="risk_aversion"):
        optimize_allocation(
            expected_returns=np.array([0.01]),
            cov_matrix=np.array([[0.0001]]),
            wallet_caps={"A": 100.0},
            wallet_of=["A"],
            max_per_opp=np.array([100.0]),
            risk_aversion=-1.0,
        )


def test_optimize_allocation_raises_on_missing_wallet_cap():
    with pytest.raises(ValueError, match="wallet_caps missing"):
        optimize_allocation(
            expected_returns=np.array([0.01]),
            cov_matrix=np.array([[0.0001]]),
            wallet_caps={"A": 100.0},
            wallet_of=["B"],
            max_per_opp=np.array([100.0]),
        )


# ── build_allocation_inputs (adapter) ────────────────────────────────────────────

def test_build_allocation_inputs_spatial_return_and_variance():
    # net_spread 100 over capital 100_000 → r = 0.001, σ² = r² = 1e-6.
    inputs = build_allocation_inputs([_spatial_opp(net_spread=100.0)], [], _wallets())

    assert inputs.kinds == ["spatial"]
    assert inputs.expected_returns[0] == pytest.approx(0.001, rel=1e-9)
    assert inputs.cov_matrix[0, 0] == pytest.approx(1e-6, rel=1e-9)
    assert inputs.max_per_opp[0] == pytest.approx(100_000.0, rel=1e-9)
    assert inputs.wallet_of[0] == Exchange.KRAKEN.value


def test_build_allocation_inputs_diagonal_variance_is_return_squared():
    inputs = build_allocation_inputs([_spatial_opp(net_spread=250.0)], [], _wallets())

    r = inputs.expected_returns[0]
    assert inputs.cov_matrix[0, 0] == pytest.approx(r ** 2, rel=1e-12)


def test_build_allocation_inputs_combines_spatial_and_triangular():
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=100_500.0, ask=100_510.0),
    }
    tri = detect_triangular(state, stablecoin_cost=0.0)
    assert tri  # precondition: a triangular opp exists

    inputs = build_allocation_inputs([_spatial_opp()], tri, _wallets())

    assert inputs.kinds == ["spatial", "triangular"]
    # Triangular BUY leg is on Binance → draws from the Binance wallet.
    assert inputs.wallet_of[1] == Exchange.BINANCE.value
    assert inputs.expected_returns[1] == pytest.approx(tri[0].net_profit_pct / 100.0, rel=1e-9)


def test_build_allocation_inputs_wallet_caps_from_balances():
    inputs = build_allocation_inputs([_spatial_opp()], [], _wallets(usdt=7_500.0))

    assert inputs.wallet_caps[Exchange.KRAKEN.value] == pytest.approx(7_500.0)


def test_build_inputs_then_optimize_respects_wallet_cap():
    # Two spatial opps on the same wallet (Kraken), cap 1_000 USDT. Total
    # allocation must not exceed the cap.
    opps = [_spatial_opp(net_spread=100.0), _spatial_opp(net_spread=200.0)]
    inputs = build_allocation_inputs(opps, [], _wallets(usdt=1_000.0))
    result = optimize_allocation(
        inputs.expected_returns, inputs.cov_matrix, inputs.wallet_caps,
        inputs.wallet_of, inputs.max_per_opp, risk_aversion=1.0,
    )
    assert result.allocations.sum() <= 1_000.0 + 1e-6
