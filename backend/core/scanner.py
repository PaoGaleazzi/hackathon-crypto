from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from itertools import permutations

import data.bbo_state as bbo_state_module
from core.fees import calculate_net_spread
from core.liquidity_health import get_liquidity_monitor
from models.market import BBO, Exchange, Opportunity

logger = logging.getLogger(__name__)


def scan_for_opportunities(bbo_state: dict[Exchange, BBO]) -> list[Opportunity]:
    """Evaluate all N*(N-1) directed pairs for arbitrage. Phase 1."""
    if len(bbo_state) < 2:
        return []

    opportunities: list[Opportunity] = []
    now = datetime.now(timezone.utc)
    monitor = get_liquidity_monitor()

    for bbo_buy, bbo_sell in permutations(bbo_state.values(), 2):
        if bbo_buy.ask >= bbo_sell.bid:
            continue

        available_qty = min(bbo_buy.ask_qty, bbo_sell.bid_qty)
        gross_spread = (bbo_sell.bid - bbo_buy.ask) * available_qty
        net_spread = calculate_net_spread(
            buy_exchange=bbo_buy.exchange,
            sell_exchange=bbo_sell.exchange,
            buy_ask=bbo_buy.ask,
            sell_bid=bbo_sell.bid,
            qty=available_qty,
            buy_depth_qty=bbo_buy.ask_qty,
            sell_depth_qty=bbo_sell.bid_qty,
        )

        if net_spread <= 0:
            continue

        degraded = not monitor.is_healthy(bbo_buy.exchange) or not monitor.is_healthy(bbo_sell.exchange)

        opportunities.append(
            Opportunity(
                buy_exchange=bbo_buy.exchange,
                sell_exchange=bbo_sell.exchange,
                buy_ask=bbo_buy.ask,
                sell_bid=bbo_sell.bid,
                gross_spread=gross_spread,
                net_spread=net_spread,
                # Phase 1: net spread % as score. OpportunityScorer replaces in Phase 3.
                score=(bbo_sell.bid - bbo_buy.ask) / bbo_buy.ask,
                detected_at=now,
                available_qty=available_qty,
                optimal_qty=available_qty,
                degraded_liquidity=degraded,
            )
        )

    return opportunities


async def run() -> None:
    """
    Scanner loop: wakes on every BBO update, scans all pairs, logs opportunities.
    Latency pipeline: ws_received_at (in BBO) → scanned_at (here).
    """
    event = bbo_state_module.get_update_event()
    while True:
        try:
            await event.wait()
            event.clear()

            scanned_at = datetime.now(timezone.utc)
            state = bbo_state_module.get_all()
            opportunities = scan_for_opportunities(state)

            for opp in opportunities:
                trigger_bbo = state.get(opp.buy_exchange)
                latency_ms = (
                    (scanned_at - trigger_bbo.ws_received_at).total_seconds() * 1000
                    if trigger_bbo else 0.0
                )
                logger.info(
                    "OPPORTUNITY | buy %-8s @ %10.2f | sell %-8s @ %10.2f | "
                    "qty=%.5f BTC | gross=$%.4f | net=$%.4f | spread=%.4f%% | latency=%.2fms",
                    opp.buy_exchange.value.upper(), opp.buy_ask,
                    opp.sell_exchange.value.upper(), opp.sell_bid,
                    opp.available_qty,
                    opp.gross_spread,
                    opp.net_spread,
                    opp.score * 100,
                    latency_ms,
                )

        except asyncio.CancelledError:
            logger.info("Scanner stopped")
            raise
        except Exception as exc:
            logger.exception("Scanner error: %s", exc)
