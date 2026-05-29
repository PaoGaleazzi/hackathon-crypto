from __future__ import annotations

import cvxpy as cp

from config import settings
from core.fees import calculate_net_spread
from models.market import Opportunity

DEFAULT_MAX_POSITION_SIZE = 1.0  # BTC, hard risk limit per trade
DEFAULT_MIN_TRADE_SIZE = settings.min_trade_size_btc  # centralized in config.settings


class InsufficientBalanceError(Exception):
    """Raised when the buy-side USDT balance cannot fund the minimum trade size."""


class OptimalSizer:
    """
    Computes q* (BTC quantity) that maximizes net profit of an arbitrage
    opportunity via a linear program (cvxpy):

        maximize    q * net_spread_per_unit
        subject to  q <= available_qty            (order book depth)
                    q <= balance_usdt / buy_ask   (buy-side wallet)
                    q <= max_position_size        (risk limit)
                    q >= min_trade_size
                    q >= 0

    NOTE: with linear taker fees the objective is linear, so the optimum is
    degenerate (it sits at the tightest upper bound). cvxpy is used for the
    optimization framing and to keep the door open for the Phase 3 quadratic
    market-impact term, where the optimum is interior.
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

    def compute_optimal_qty(self, opportunity: Opportunity, balance_usdt: float) -> float:
        """Return q* in BTC (always >= 0). Raises InsufficientBalanceError if the
        buy-side balance cannot fund min_trade_size."""
        if balance_usdt < 0:
            raise ValueError(f"balance_usdt must be non-negative, got {balance_usdt}")

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

        q = cp.Variable(nonneg=True)
        constraints = [
            q <= opportunity.available_qty,
            q <= balance_cap,
            q <= self.max_position_size,
            q >= self.min_trade_size,
        ]
        problem = cp.Problem(cp.Maximize(q * net_spread_per_unit), constraints)
        problem.solve()

        if problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) or q.value is None:
            raise RuntimeError(f"LP solver failed with status {problem.status!r}")

        # Clamp tiny negative/overshoot from solver numerics into the feasible box.
        return float(min(max(q.value, 0.0), upper_bound))
