from __future__ import annotations

import numpy as np
import pytest

from core.allocator import optimize_allocation


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
