from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from itertools import permutations

import data.bbo_state as bbo_state_module
from core.fees import calculate_net_spread
from core.liquidity_health import get_liquidity_monitor
from core.microprice import microprice
from models.market import BBO, Exchange, Opportunity

logger = logging.getLogger(__name__)


def evaluate_microprice_signal(bbo_buy: BBO, bbo_sell: BBO) -> tuple[float, float, bool]:
    """
    Micro-price quality signal for a buy@buy_exchange / sell@sell_exchange opportunity.

    Returns (microprice_buy, microprice_sell, confirms).

    Why directional pressure, not an absolute level comparison:
      The micro-price is bounded inside its own exchange's [bid, ask]. Since a
      real opportunity requires buy_ask < sell_bid, we always have
      microprice_buy <= buy_ask < sell_bid <= microprice_sell — so comparing the
      micro-prices across exchanges (or against the opposite leg's quote) is
      degenerate and always "confirms". The only non-trivial information the
      micro-price carries here is the *direction* of short-term pressure within
      each book, read off the sign of (micro - mid):

        - buy leg:  micro > mid  → buy-side pressure → the buy_exchange price is
          about to tick UP → buy_ask rises → spread erodes. Adverse.
        - sell leg: micro < mid  → sell-side pressure → the sell_exchange price is
          about to tick DOWN → sell_bid falls → spread erodes. Adverse.

      The spread is expected to persist (confirms=True) only when neither leg
      shows adverse pressure: micro_buy <= mid_buy AND micro_sell >= mid_sell.
      A balanced book (micro == mid) is neutral and confirms.
    """
    micro_buy = microprice(bbo_buy.bid, bbo_buy.ask, bbo_buy.bid_qty, bbo_buy.ask_qty)
    micro_sell = microprice(bbo_sell.bid, bbo_sell.ask, bbo_sell.bid_qty, bbo_sell.ask_qty)
    mid_buy = (bbo_buy.bid + bbo_buy.ask) / 2.0
    mid_sell = (bbo_sell.bid + bbo_sell.ask) / 2.0
    confirms = micro_buy <= mid_buy and micro_sell >= mid_sell
    return micro_buy, micro_sell, confirms


def scan_for_opportunities(
    bbo_state: dict[Exchange, BBO], now: datetime | None = None
) -> list[Opportunity]:
    """Evaluate all N*(N-1) directed pairs for arbitrage. Phase 1.

    ``now`` stamps each Opportunity's ``detected_at``; defaults to wall-clock time.
    Replay/backtests pass the tick clock so detection is fully deterministic."""
    if len(bbo_state) < 2:
        return []

    opportunities: list[Opportunity] = []
    if now is None:
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

        micro_buy, micro_sell, microprice_confirms = evaluate_microprice_signal(
            bbo_buy, bbo_sell
        )

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
                microprice_buy=micro_buy,
                microprice_sell=micro_sell,
                microprice_confirms=microprice_confirms,
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
