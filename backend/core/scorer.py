from __future__ import annotations

from datetime import datetime, timezone

from models.market import Opportunity


def score_opportunity(opportunity: Opportunity, now: datetime) -> float:
    """
    Composite score for priority queue ordering. Higher = better.
    score = (net_spread_pct * available_qty * liquidity_score) / latency_ms
    """
    latency_ms = max(1.0, (now - opportunity.detected_at).total_seconds() * 1000)
    net_spread_pct = opportunity.net_spread / (opportunity.buy_ask * opportunity.available_qty)
    liquidity_score = (
        min(1.0, opportunity.available_qty / opportunity.optimal_qty)
        if opportunity.optimal_qty > 0
        else 1.0
    )
    return (net_spread_pct * opportunity.available_qty * liquidity_score) / latency_ms


def rank_opportunities(
    opportunities: list[Opportunity],
    now: datetime | None = None,
) -> list[Opportunity]:
    """Return opportunities sorted by score descending, with score field updated."""
    if not opportunities:
        return []

    _now = now if now is not None else datetime.now(timezone.utc)
    scored = [
        opp.model_copy(update={"score": score_opportunity(opp, _now)})
        for opp in opportunities
    ]
    return sorted(scored, key=lambda o: o.score, reverse=True)
