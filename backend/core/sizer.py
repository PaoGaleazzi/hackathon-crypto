from __future__ import annotations

import cvxpy as cp

from config import settings
from core.fees import calculate_net_spread
from models.market import Opportunity

DEFAULT_MAX_POSITION_SIZE = 1.0  # BTC, hard risk limit per trade
DEFAULT_MIN_TRADE_SIZE = settings.min_trade_size_btc  # centralized in config.settings

# Market-impact intensity for the quadratic slippage term. With IMPACT_COEFF = 1,
# walking the full top-of-book depth costs ~one gross spread in slippage. Tune up
# to penalize size more aggressively.
DEFAULT_IMPACT_COEFF = 1.0


class InsufficientBalanceError(Exception):
    """Raised when the buy-side USDT balance cannot fund the minimum trade size."""


def estimate_market_impact(
    opportunity: Opportunity,
    impact_coeff: float = DEFAULT_IMPACT_COEFF,
) -> float:
    """
    Estimate the quadratic market-impact coefficient λ (USDT per BTC²) from the
    order book, following the depth model:

        λ = impact_coeff · spread_at_depth / total_volume_available
          = impact_coeff · (sell_bid − buy_ask) / available_qty

    Intuition: a wide cross-exchange spread sitting on thin depth means liquidity
    is scarce — consuming it moves the price fast, so impact is steep. Recomputed
    every tick from live BBO depth, never hardcoded.

    Returns 0.0 when depth or spread is unavailable; the caller then falls back to
    the linear edge (degenerate optimum at the tightest constraint).
    """
    gross_spread_per_unit = opportunity.sell_bid - opportunity.buy_ask
    if gross_spread_per_unit <= 0 or opportunity.available_qty <= 0:
        return 0.0
    return impact_coeff * gross_spread_per_unit / opportunity.available_qty


class OptimalSizer:
    """
    Computes q* (BTC quantity) maximizing net profit of an arbitrage opportunity
    under a quadratic market-impact model, via a QP (cvxpy):

        maximize    q·s − λ·q²
        subject to  q <= available_qty            (order book depth)
                    q <= balance_usdt / buy_ask   (buy-side wallet)
                    q <= max_position_size        (risk limit)
                    q >= min_trade_size

    where s = net spread per unit (USDT/BTC, gross edge net of taker fees) and
    λ = market-impact coefficient (USDT/BTC²) estimated from order book depth.

    The objective is strictly concave (λ > 0), so the unconstrained optimum is
    INTERIOR — the classic analytic result q* = s / (2λ) — not pinned to a
    constraint boundary. This is the difference from a greedy "fill all available
    liquidity" bot: past q*, the marginal spread no longer covers the marginal
    slippage, so trading more destroys profit. cvxpy solves the constrained QP;
    when the analytic optimum sits inside the feasible box it is returned exactly,
    otherwise the binding constraint caps it.

    With λ = 0 the objective collapses to the linear (degenerate) LP, kept as a
    fallback for when depth data is unavailable.
    """

    def __init__(
        self,
        max_position_size: float = DEFAULT_MAX_POSITION_SIZE,
        min_trade_size: float = DEFAULT_MIN_TRADE_SIZE,
    ) -> None:
        if min_trade_size <= 0:
            raise ValueError(f"min_trade_size must be positive, got {min_trade_size}")
        if max_position_size < min_trade_size:
            raise ValueError(
                f"max_position_size ({max_position_size}) must be >= "
                f"min_trade_size ({min_trade_size})"
            )
        self.max_position_size = max_position_size
        self.min_trade_size = min_trade_size

    def compute_optimal_qty(
        self,
        opportunity: Opportunity,
        balance_usdt: float,
        market_impact: float | None = None,
    ) -> float:
        """Return q* in BTC (always >= 0). Raises InsufficientBalanceError if the
        buy-side balance cannot fund min_trade_size.

        market_impact (λ): pass None to estimate it from the order book, 0.0 to
        force the linear fallback, or an explicit value to override.
        """
        if balance_usdt < 0:
            raise ValueError(f"balance_usdt must be non-negative, got {balance_usdt}")

        # Linear edge per unit (USDT/BTC), net of taker fees on both legs.
        net_spread_per_unit = calculate_net_spread(
            buy_exchange=opportunity.buy_exchange,
            sell_exchange=opportunity.sell_exchange,
            buy_ask=opportunity.buy_ask,
            sell_bid=opportunity.sell_bid,
            qty=1.0,
        )
        # Defensive: scanner only emits net_spread > 0, but never trade an
        # unprofitable opportunity if one slips through.
        if net_spread_per_unit <= 0:
            return 0.0

        balance_cap = balance_usdt / opportunity.buy_ask
        if balance_cap < self.min_trade_size:
            raise InsufficientBalanceError(
                f"balance {balance_usdt} USDT funds only {balance_cap:.6f} BTC at "
                f"ask {opportunity.buy_ask}, below min_trade_size {self.min_trade_size}"
            )

        upper_bound = min(opportunity.available_qty, balance_cap, self.max_position_size)
        # Liquidity/risk caps (not balance) can't reach the minimum order size:
        # not a funding error, just nothing tradable here.
        if upper_bound < self.min_trade_size:
            return 0.0

        lam = (
            estimate_market_impact(opportunity)
            if market_impact is None
            else market_impact
        )
        if lam < 0:
            raise ValueError(f"market_impact (λ) must be non-negative, got {lam}")

        q = cp.Variable(nonneg=True)
        constraints = [q <= upper_bound, q >= self.min_trade_size]
        if lam > 0:
            objective = cp.Maximize(q * net_spread_per_unit - lam * cp.square(q))
        else:
            # Degenerate linear fallback: optimum sits at the tightest upper bound.
            objective = cp.Maximize(q * net_spread_per_unit)
        problem = cp.Problem(objective, constraints)
        problem.solve()

        if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) or q.value is None:
            raise RuntimeError(f"QP solver failed with status {problem.status!r}")

        # Clamp tiny negative/overshoot from solver numerics into the feasible box.
        q_star = float(min(max(q.value, 0.0), upper_bound))

        # The min_trade_size floor can force a quantity whose slippage exceeds the
        # edge. Don't trade if net of impact is non-positive.
        if q_star * net_spread_per_unit - lam * q_star**2 <= 0:
            return 0.0
        return q_star
