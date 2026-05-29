from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.scanner import evaluate_microprice_signal, scan_for_opportunities
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
    # scanner passes depth_qty so calculate_net_spread includes all 4 cost components:
    #   gross        = (70_500 - 70_000) * 0.8                               = 400.0
    #   fee_buy      = 0.8 * 70_000 * 0.001                                  =  56.0
    #   fee_sell     = 0.8 * 70_500 * 0.0026                                 = 146.64
    #   withdrawal   = 0.0005 * 70_000                                        =  35.0
    #   slippage_buy = 0.001 * sqrt(0.8/1.0) * 0.8 * 70_000                 ≈  50.09
    #   slippage_sell= 0.001 * sqrt(0.8/0.8) * 0.8 * 70_500                 ≈  56.40
    #   latency_buy  ≈ 0.8 * 70_000 * vol_per_ms * 5ms                      ≈   1.26
    #   latency_sell ≈ 0.8 * 70_500 * vol_per_ms * 50ms                     ≈  12.70
    #   net ≈ 400 - 56 - 146.64 - 35 - 50.09 - 56.40 - 1.26 - 12.70       ≈  41.91
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, ask_qty=1.0),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=70_500.0, ask=71_000.0, bid_qty=0.8),
    }
    opps = scan_for_opportunities(state)
    assert len(opps) == 1
    opp = opps[0]
    assert opp.net_spread == pytest.approx(41.906838150415346, rel=1e-4)
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


# ── evaluate_microprice_signal: known-answer cases ────────────────────────────

def test_microprice_signal_balanced_books_confirm():
    # Both books balanced (bid_qty == ask_qty) → micro == mid on each leg.
    # No adverse pressure → confirms.
    buy = _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, bid_qty=1.0, ask_qty=1.0)
    sell = _bbo(Exchange.KRAKEN, bid=70_500.0, ask=70_600.0, bid_qty=1.0, ask_qty=1.0)
    micro_buy, micro_sell, confirms = evaluate_microprice_signal(buy, sell)
    assert micro_buy == pytest.approx(69_950.0)
    assert micro_sell == pytest.approx(70_550.0)
    assert confirms is True


def test_microprice_signal_favorable_pressure_confirms():
    # buy leg: heavy ask volume → micro near bid → micro < mid → price likely to
    #   fall → buy even cheaper. Favorable.
    # sell leg: heavy bid volume → micro near ask → micro > mid → price likely to
    #   rise → sell even higher. Favorable.
    buy = _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, bid_qty=1.0, ask_qty=100.0)
    sell = _bbo(Exchange.KRAKEN, bid=70_500.0, ask=70_600.0, bid_qty=100.0, ask_qty=1.0)
    micro_buy, micro_sell, confirms = evaluate_microprice_signal(buy, sell)
    assert micro_buy < 69_950.0  # below mid
    assert micro_sell > 70_550.0  # above mid
    assert confirms is True


def test_microprice_signal_buy_side_adverse_pressure_denies():
    # buy leg: heavy bid volume → micro near ask → micro > mid → buy_exchange about
    #   to tick UP → buy_ask rises → spread erodes. Adverse → denies.
    # micro_buy = (70_000·100 + 69_900·1) / 101 = 7_069_900 / 101 = 69_999.00990...
    buy = _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, bid_qty=100.0, ask_qty=1.0)
    sell = _bbo(Exchange.KRAKEN, bid=70_500.0, ask=70_600.0, bid_qty=1.0, ask_qty=1.0)
    micro_buy, _, confirms = evaluate_microprice_signal(buy, sell)
    assert micro_buy == pytest.approx(69_999.00990099, rel=1e-9)
    assert micro_buy > 69_950.0  # above mid → adverse
    assert confirms is False


def test_microprice_signal_sell_side_adverse_pressure_denies():
    # sell leg: heavy ask volume → micro near bid → micro < mid → sell_exchange about
    #   to tick DOWN → sell_bid falls → spread erodes. Adverse → denies.
    # micro_sell = (70_600·1 + 70_500·100) / 101 = 7_120_600 / 101 = 70_500.99009...
    buy = _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, bid_qty=1.0, ask_qty=1.0)
    sell = _bbo(Exchange.KRAKEN, bid=70_500.0, ask=70_600.0, bid_qty=1.0, ask_qty=100.0)
    _, micro_sell, confirms = evaluate_microprice_signal(buy, sell)
    assert micro_sell == pytest.approx(70_500.99009901, rel=1e-9)
    assert micro_sell < 70_550.0  # below mid → adverse
    assert confirms is False


# ── scanner integration: micro-price fields stamped on Opportunity ────────────

def test_scan_stamps_microprice_fields_and_confirms():
    # Balanced books both legs → micro == mid → confirms.
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, bid_qty=1.0, ask_qty=1.0),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=70_800.0, ask=70_900.0, bid_qty=1.0, ask_qty=1.0),
    }
    opps = scan_for_opportunities(state)
    assert len(opps) == 1
    opp = opps[0]
    assert opp.microprice_buy == pytest.approx(69_950.0)
    assert opp.microprice_sell == pytest.approx(70_850.0)
    assert opp.microprice_confirms is True


def test_scan_microprice_denies_on_adverse_sell_pressure():
    # sell leg heavily ask-weighted → micro below mid → spread erosion → denies.
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=69_900.0, ask=70_000.0, bid_qty=1.0, ask_qty=1.0),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  bid=71_000.0, ask=72_000.0, bid_qty=0.8, ask_qty=8.0),
    }
    opps = scan_for_opportunities(state)
    assert len(opps) == 1
    opp = opps[0]
    assert opp.buy_exchange == Exchange.BINANCE
    assert opp.microprice_confirms is False
