from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import cvxpy as cp
import numpy as np

from core.fill_probability import DEFAULT_TAU_MS, expected_profit, fill_probability
from core.triangular import TriangularOpportunity
from models.market import Exchange, Opportunity
from models.trade import WalletBalance

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


# ── adapter: opportunities → optimizer inputs ────────────────────────────────────


@dataclass(frozen=True)
class AllocationInputs:
    opportunities: list           # source objects (Opportunity | TriangularOpportunity)
    kinds: list[str]              # "spatial" | "triangular", parallel to opportunities
    expected_returns: np.ndarray  # r_i, net profit per unit capital
    cov_matrix: np.ndarray        # diagonal, σ_i² = r_i² / P_fill_i
    wallet_caps: dict[str, float]
    wallet_of: list[str]
    max_per_opp: np.ndarray


def build_allocation_inputs(
    spatial: list[Opportunity],
    triangular: list[TriangularOpportunity],
    wallets: dict[Exchange, WalletBalance],
    now: datetime | None = None,
    tau_ms: float = DEFAULT_TAU_MS,
) -> AllocationInputs:
    """Assemble optimize_allocation() inputs from live opportunities and balances.

    expected_return r_i is the net return per unit capital:
      - spatial:     E[profit](opp, now) / (available_qty · buy_ask), where E[profit]
                     weights net_spread by the fill probability (exp decay with the
                     opportunity's age) and subtracts the failure penalty. Capital
                     is steered by *realizable* edge, not gross spread.
      - triangular:  net_profit_pct / 100   (fees-only; the fixed withdrawal is a
                     non-linear charge, kept on the opportunity, not in r)

    Covariance is diagonal with the proxy σ_i² = r_i² / P_fill_i. The 1/P_fill
    factor inflates the perceived risk of stale opportunities, so they are
    penalized TWICE: lower expected return (via E[profit]) AND higher variance.
    Because the interior optimum is x* = r_i/(2λ·σ_i²) = P_fill·/(2λ·r_i), a stale
    spatial opportunity is starved on both the mean and the risk term. Triangular
    legs have no latency-decay model, so P_fill = 1 (σ_i² = r_i²).
    """
    _now = now if now is not None else datetime.now(timezone.utc)
    opportunities: list = []
    kinds: list[str] = []
    returns: list[float] = []
    variances: list[float] = []
    wallet_of: list[str] = []
    max_per_opp: list[float] = []

    for opp in spatial:
        capital_basis = opp.available_qty * opp.buy_ask
        if capital_basis <= 0:
            continue
        latency_ms = max(0.0, (_now - opp.detected_at).total_seconds() * 1000.0)
        p_fill = fill_probability(latency_ms, tau_ms)
        r_i = expected_profit(opp, _now, tau_ms=tau_ms) / capital_basis
        opportunities.append(opp)
        kinds.append("spatial")
        returns.append(r_i)
        variances.append(r_i**2 / p_fill)
        wallet_of.append(opp.buy_exchange.value)
        max_per_opp.append(capital_basis)

    for opp in triangular:
        buy_leg = opp.legs[0]
        if buy_leg.exchange is None:
            continue
        r_i = opp.net_profit_pct / 100.0
        opportunities.append(opp)
        kinds.append("triangular")
        returns.append(r_i)
        variances.append(r_i**2)
        wallet_of.append(buy_leg.exchange.value)
        max_per_opp.append(opp.notional)

    returns_arr = np.array(returns, dtype=float)
    cov = np.diag(np.array(variances, dtype=float)) if variances else np.zeros((0, 0))
    wallet_caps = {ex.value: wb.usdt for ex, wb in wallets.items()}

    return AllocationInputs(
        opportunities=opportunities,
        kinds=kinds,
        expected_returns=returns_arr,
        cov_matrix=cov,
        wallet_caps=wallet_caps,
        wallet_of=wallet_of,
        max_per_opp=np.array(max_per_opp, dtype=float),
    )


def allocation_to_dict(inputs: AllocationInputs, result: AllocationResult) -> dict:
    """JSON-serializable portfolio view for the `allocation` WS broadcast."""
    items = []
    for i, (opp, kind) in enumerate(zip(inputs.opportunities, inputs.kinds)):
        label = (
            opp.path if kind == "triangular"
            else f"{opp.buy_exchange.value}→{opp.sell_exchange.value}"
        )
        items.append({
            "kind": kind,
            "label": label,
            "wallet": inputs.wallet_of[i],
            "expected_return": float(inputs.expected_returns[i]),
            "allocation": float(result.allocations[i]),
            "max_allocation": float(inputs.max_per_opp[i]),
        })
    return {
        "expected_profit": result.expected_profit,
        "expected_variance": result.expected_variance,
        "objective_value": result.objective_value,
        "n_opportunities": len(items),
        "items": items,
    }
