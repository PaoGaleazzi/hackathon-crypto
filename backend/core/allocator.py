from __future__ import annotations

from dataclasses import dataclass

import cvxpy as cp
import numpy as np

DEFAULT_RISK_AVERSION = 1.0  # λ in the mean-variance objective


@dataclass(frozen=True)
class AllocationResult:
    allocations: np.ndarray   # x*, capital allocated per opportunity (len n)
    expected_profit: float    # rᵀx  (mean term)
    expected_variance: float  # xᵀΣx (risk term, before λ)
    objective_value: float    # rᵀx − λ·xᵀΣx
    status: str               # cvxpy solver status


def optimize_allocation(
    expected_returns: np.ndarray,
    cov_matrix: np.ndarray,
    wallet_caps: dict[str, float],
    wallet_of: list[str],
    max_per_opp: np.ndarray,
    risk_aversion: float = DEFAULT_RISK_AVERSION,
) -> AllocationResult:
    """Mean-variance capital allocation across simultaneous arbitrage opportunities.

        maximize    rᵀx − λ·xᵀΣx
        subject to  0 <= x_i <= max_per_opp_i              (per-opportunity limit)
                    Σ_{i drawn on wallet w} x_i <= cap_w   (per-wallet balance)

    where x_i is capital (e.g. USDT) committed to opportunity i, r_i its expected
    profit per unit capital, and Σ the covariance of the per-unit returns. The
    objective is concave for any PSD Σ, so cvxpy returns the global optimum.

    With λ = 0 the problem collapses to an LP (allocate greedily to the binding
    constraints) — the analogue of the linear fallback in OptimalSizer.
    """
    r = np.asarray(expected_returns, dtype=float)
    n = r.shape[0]
    if n == 0:
        return AllocationResult(
            allocations=np.zeros(0),
            expected_profit=0.0,
            expected_variance=0.0,
            objective_value=0.0,
            status=cp.OPTIMAL,
        )

    cov = np.asarray(cov_matrix, dtype=float)
    upper = np.asarray(max_per_opp, dtype=float)
    if cov.shape != (n, n):
        raise ValueError(f"cov_matrix must be {(n, n)}, got {cov.shape}")
    if upper.shape != (n,):
        raise ValueError(f"max_per_opp must be {(n,)}, got {upper.shape}")
    if len(wallet_of) != n:
        raise ValueError(f"wallet_of must have length {n}, got {len(wallet_of)}")
    if risk_aversion < 0:
        raise ValueError(f"risk_aversion (λ) must be >= 0, got {risk_aversion}")
    if np.any(upper < 0):
        raise ValueError("max_per_opp entries must be non-negative")
    missing = set(wallet_of) - wallet_caps.keys()
    if missing:
        raise ValueError(f"wallet_caps missing entries for wallets: {sorted(missing)}")

    x = cp.Variable(n, nonneg=True)
    profit = r @ x
    if risk_aversion > 0:
        # psd_wrap: trust the caller's covariance is PSD, skip cvxpy's check.
        objective = cp.Maximize(profit - risk_aversion * cp.quad_form(x, cp.psd_wrap(cov)))
    else:
        objective = cp.Maximize(profit)

    constraints = [x <= upper]
    for wallet, cap in wallet_caps.items():
        mask = np.fromiter((w == wallet for w in wallet_of), dtype=float, count=n)
        if mask.any():
            constraints.append(mask @ x <= cap)

    problem = cp.Problem(objective, constraints)
    problem.solve()

    if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) or x.value is None:
        raise RuntimeError(f"allocation QP failed with status {problem.status!r}")

    # Clamp solver numerics into the feasible box [0, upper].
    allocations = np.clip(x.value, 0.0, upper)
    expected_profit = float(r @ allocations)
    expected_variance = float(allocations @ cov @ allocations)
    objective_value = expected_profit - risk_aversion * expected_variance

    return AllocationResult(
        allocations=allocations,
        expected_profit=expected_profit,
        expected_variance=expected_variance,
        objective_value=objective_value,
        status=problem.status,
    )
