from __future__ import annotations

from datetime import datetime, timezone

from core.fill_probability import DEFAULT_TAU_MS, expected_profit
from models.market import Opportunity

# Score multiplier applied when either leg's exchange has DEGRADED liquidity.
# Reflects higher slippage risk from fragmented books: wider effective spreads
# and more price impact than the model can see from BBO alone.
DEGRADED_LIQUIDITY_PENALTY = 0.5

# Score multiplier applied when the micro-price does NOT confirm the spread,
# i.e. short-term order-book pressure on at least one leg is eroding it
# (see scanner.evaluate_microprice_signal). Same magnitude as the liquidity
# penalty: a discount, not a discard — the spread may still hold.
MICROPRICE_PENALTY = 0.5


def score_opportunity(
    opportunity: Opportunity, now: datetime, tau_ms: float = DEFAULT_TAU_MS
) -> float:
    """
    Composite score for priority queue ordering. Higher = better.

    Ranks by latency-adjusted expected profit (E[profit]), not gross profit:
    the fill-probability decay penalizes stale opportunities, the liquidity
    score discounts opportunities we cannot fill at their optimal size, the
    degraded-liquidity penalty reduces the score when either leg's exchange
    has a fragmented order book, and the micro-price penalty reduces it when
    short-term book pressure is eroding the spread.
    """
    e_profit = expected_profit(opportunity, now, tau_ms=tau_ms)
    liquidity_score = (
        min(1.0, opportunity.available_qty / opportunity.optimal_qty)
        if opportunity.optimal_qty > 0
        else 1.0
    )
    score = e_profit * liquidity_score
    if opportunity.degraded_liquidity:
        score *= DEGRADED_LIQUIDITY_PENALTY
    if not opportunity.microprice_confirms:
        score *= MICROPRICE_PENALTY
    return score


def rank_opportunities(
    opportunities: list[Opportunity],
    now: datetime | None = None,
    tau_ms: float = DEFAULT_TAU_MS,
) -> list[Opportunity]:
    """Return opportunities sorted by score descending, with score field updated."""
    if not opportunities:
        return []

    _now = now if now is not None else datetime.now(timezone.utc)
    scored = [
        opp.model_copy(update={"score": score_opportunity(opp, _now, tau_ms)})
        for opp in opportunities
    ]
    return sorted(scored, key=lambda o: o.score, reverse=True)
