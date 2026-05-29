from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.scanner import scan_for_opportunities
from models.market import BBO, Exchange

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)


def _bbo(exchange: Exchange, bid: float, ask: float, bid_qty: float = 1.0, ask_qty: float = 1.0) -> BBO:
    return BBO(exchange=exchange, bid=bid, ask=ask, bid_qty=bid_qty, ask_qty=ask_qty, ws_received_at=_NOW)


# ── empty / insufficient data ─────────────────────────────────────────────────

def test_scan_returns_empty_on_empty_state():
    assert scan_for_opportunities({}) == []


def test_scan_returns_empty_on_single_exchange():
    state = {Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=70_000.0, ask=70_001.0)}
    assert scan_for_opportunities(state) == []


# ── no price cross ────────────────────────────────────────────────────────────

def test_scan_returns_empty_when_no_price_cross():
    # BINANCE ask=70_100 >= KRAKEN bid=70_000 in both directions → no cross
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=70_050.0, ask=70_100.0),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=70_000.0, ask=70_050.0),
    }
    assert scan_for_opportunities(state) == []


# ── fees dominate ─────────────────────────────────────────────────────────────

def test_scan_returns_empty_when_spread_positive_but_fees_dominate():
    # Price cross exists but net < 0:
    # buy BINANCE ask=70_000, sell KRAKEN bid=70_020, qty=0.1
    # gross=2.0, fee_buy=7.0, fee_sell=18.2 → net ≈ -23.2
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=69_990.0, ask=70_000.0, ask_qty=0.1),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=70_020.0, ask=70_100.0, bid_qty=0.1),
    }
    assert scan_for_opportunities(state) == []


# ── profitable opportunity ────────────────────────────────────────────────────

def test_scan_detects_profitable_opportunity_known_answer():
    # buy BINANCE ask=70_000, sell KRAKEN bid=70_500, qty=min(1.0, 0.8)=0.8
    # gross   = (70_500 - 70_000) * 0.8 = 400.0
    # fee_buy = 0.8 * 70_000 * 0.001   =  56.0
    # fee_sell= 0.8 * 70_500 * 0.0026  = 146.64
    # net     = 400.0 - 56.0 - 146.64  = 197.36
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, ask_qty=1.0),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=70_500.0, ask=71_000.0, bid_qty=0.8),
    }
    opps = scan_for_opportunities(state)
    assert len(opps) == 1
    opp = opps[0]
    assert opp.net_spread == pytest.approx(197.36)
    assert opp.gross_spread == pytest.approx(400.0)
    assert opp.available_qty == pytest.approx(0.8)


def test_scan_direction_is_correct():
    # Only BINANCE→KRAKEN is profitable; reverse has no price cross
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=69_800.0, ask=70_000.0, ask_qty=1.0),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=70_500.0, ask=71_000.0, bid_qty=0.8),
    }
    opps = scan_for_opportunities(state)
    assert len(opps) == 1
    assert opps[0].buy_exchange == Exchange.BINANCE
    assert opps[0].sell_exchange == Exchange.KRAKEN


def test_scan_available_qty_is_min_of_depths():
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, ask_qty=2.0),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=70_500.0, ask=71_000.0, bid_qty=0.3),
    }
    opps = scan_for_opportunities(state)
    assert len(opps) == 1
    assert opps[0].available_qty == pytest.approx(0.3)


def test_scan_sets_detected_at_utc_timestamp():
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=70_500.0, ask=71_000.0),
    }
    opps = scan_for_opportunities(state)
    assert len(opps) == 1
    assert opps[0].detected_at.tzinfo is not None
    assert opps[0].detected_at.tzinfo == timezone.utc


def test_scan_evaluates_all_directed_pairs_three_exchanges():
    # Three exchanges: each pair checked in both directions
    # Only BINANCE→KRAKEN and BINANCE→COINBASE are profitable
    state = {
        Exchange.BINANCE:  _bbo(Exchange.BINANCE,  bid=69_000.0, ask=70_000.0, ask_qty=1.0),
        Exchange.KRAKEN:   _bbo(Exchange.KRAKEN,   bid=70_500.0, ask=75_000.0, bid_qty=1.0),
        Exchange.COINBASE: _bbo(Exchange.COINBASE,  bid=70_500.0, ask=75_000.0, bid_qty=1.0),
    }
    opps = scan_for_opportunities(state)
    buy_exchanges = {o.buy_exchange for o in opps}
    sell_exchanges = {o.sell_exchange for o in opps}
    assert Exchange.BINANCE in buy_exchanges
    assert Exchange.KRAKEN in sell_exchanges or Exchange.COINBASE in sell_exchanges
    # KRAKEN and COINBASE don't cross each other (same ask=75_000 >= bid=70_500 only in one direction)
    for o in opps:
        assert o.net_spread > 0
