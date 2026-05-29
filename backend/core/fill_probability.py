from __future__ import annotations

import math
from datetime import datetime

from core.fees import OrderSide, calculate_fee
from models.market import Opportunity

# Decay constant (ms). At latency == TAU the fill probability is 1/e ≈ 0.368.
# Tuned so opportunities older than ~150ms (3·tau) are heavily discounted,
# matching how fast top-of-book quotes churn on liquid BTC pairs.
DEFAULT_TAU_MS: float = 50.0


def fill_probability(latency_ms: float, tau_ms: float = DEFAULT_TAU_MS) -> float:
    """
    P(order still fills) = exp(-latency_ms / tau).

    Models that older opportunities are less likely to still be on the book
    by the time our order arrives. Returns 1.0 at zero latency, decaying
    monotonically toward 0 as the opportunity ages.
    """
    if latency_ms < 0:
        raise ValueError(f"latency_ms must be non-negative, got {latency_ms}")
    if tau_ms <= 0:
        raise ValueError(f"tau_ms must be positive, got {tau_ms}")
    return math.exp(-latency_ms / tau_ms)


def estimate_failure_penalty(opportunity: Opportunity) -> float:
    """
    Cost (USDT) of a failed arb cycle: the taker fees already paid on both
    legs are sunk when the second leg fails to fill. This is the downside we
    risk every time we fire on a stale opportunity.
    """
    fee_buy = calculate_fee(
        opportunity.buy_exchange, opportunity.available_qty, opportunity.buy_ask, OrderSide.TAKER
    )
    fee_sell = calculate_fee(
        opportunity.sell_exchange, opportunity.available_qty, opportunity.sell_bid, OrderSide.TAKER
    )
    return fee_buy + fee_sell


def expected_profit(
    opportunity: Opportunity,
    now: datetime,
    tau_ms: float = DEFAULT_TAU_MS,
    penalty: float | None = None,
) -> float:
    """
    Latency-adjusted expected P&L (USDT):

        E[profit] = P_fill * net_profit - (1 - P_fill) * penalty

    where P_fill decays exponentially with the opportunity's age and penalty
    defaults to the sunk fees of a failed execution. A fresh opportunity earns
    nearly its full net_spread; a stale one is dominated by the penalty term
    and can score negative, pushing it out of the priority queue.
    """
    latency_ms = max(0.0, (now - opportunity.detected_at).total_seconds() * 1000.0)
    p_fill = fill_probability(latency_ms, tau_ms)
    if penalty is None:
        penalty = estimate_failure_penalty(opportunity)
    return p_fill * opportunity.net_spread - (1.0 - p_fill) * penalty
