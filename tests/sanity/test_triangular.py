from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.triangular import detect_triangular
from models.market import BBO, Exchange

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)


def _bbo(exchange: Exchange, bid: float, ask: float, qty: float = 1.0) -> BBO:
    return BBO(
        exchange=exchange,
        bid=bid,
        ask=ask,
        bid_qty=qty,
        ask_qty=qty,
        ws_received_at=_NOW,
    )


# ── known-answer case (computed by hand) ─────────────────────────────────────────
#
# Triangle USDT→BTC→USD→USDT:
#   leg1  buy BTC on Binance @ ask 100000, taker 0.001 → 0.999/100000 BTC per USDT
#   leg2  sell BTC on Kraken @ bid 100500, taker 0.0026 → 100500*0.9974 USD per BTC
#   leg3  convert USD→USDT with zero cost            → 1.0
# net_multiplier = 0.999 * 0.9974 * 1.005 = 1.001384613
# net_profit_pct = 0.1384613 %
_HAND_NET_MULTIPLIER = 0.999 * 0.9974 * 1.005  # == 1.0013846130


def _binance_kraken_state() -> dict[Exchange, BBO]:
    return {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=100_500.0, ask=100_510.0),
    }


def test_detect_triangular_finds_single_profitable_cycle():
    opps = detect_triangular(_binance_kraken_state(), stablecoin_cost=0.0)

    assert len(opps) == 1
    opp = opps[0]
    assert opp.path == "USDT→BTC→USD→USDT"
    assert opp.legs[0].action == "BUY"
    assert opp.legs[0].exchange == Exchange.BINANCE
    assert opp.legs[1].action == "SELL"
    assert opp.legs[1].exchange == Exchange.KRAKEN
    assert opp.legs[2].action == "CONVERT"
    assert opp.legs[2].exchange is None


def test_detect_triangular_net_multiplier_matches_hand_calc():
    opp = detect_triangular(_binance_kraken_state(), stablecoin_cost=0.0)[0]

    assert opp.net_multiplier == pytest.approx(_HAND_NET_MULTIPLIER, rel=1e-9)
    assert opp.net_profit_pct == pytest.approx(0.1384613, rel=1e-4)


def test_detect_triangular_applies_stablecoin_cost():
    # 10 bp conversion cost shaves the headline multiplier by exactly (1 - 0.001).
    opp = detect_triangular(_binance_kraken_state(), stablecoin_cost=0.001)[0]

    assert opp.net_multiplier == pytest.approx(_HAND_NET_MULTIPLIER * 0.999, rel=1e-9)


def test_detect_triangular_returns_empty_when_conversion_cost_kills_profit():
    # 20 bp conversion cost pushes the multiplier below 1.0 → no opportunity.
    opps = detect_triangular(_binance_kraken_state(), stablecoin_cost=0.002)

    assert opps == []


def test_detect_triangular_returns_empty_with_single_quote_currency():
    # Two USDT venues only: currencies are {BTC, USDT}, no third node exists, so
    # no triangle can form. This is the guard against re-deriving spatial arb.
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.OKX: _bbo(Exchange.OKX, bid=100_400.0, ask=100_410.0),
    }
    assert detect_triangular(state, stablecoin_cost=0.0) == []


def test_detect_triangular_every_opportunity_spans_three_distinct_currencies():
    opps = detect_triangular(_binance_kraken_state(), stablecoin_cost=0.0)

    assert opps  # sanity: there is something to check
    for opp in opps:
        assert len(set(opp.cycle)) == 3


def test_detect_triangular_sorts_by_profit_descending():
    # Two USDT buy venues feeding one USD sell venue → two cycles. OKX is cheaper
    # to buy on (ask 99_950 < 100_000), so its cycle must rank first.
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.OKX: _bbo(Exchange.OKX, bid=99_940.0, ask=99_950.0),
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=100_500.0, ask=100_510.0),
    }
    opps = detect_triangular(state, stablecoin_cost=0.0)

    assert len(opps) == 2
    assert opps[0].legs[0].exchange == Exchange.OKX
    assert opps[1].legs[0].exchange == Exchange.BINANCE
    assert opps[0].net_profit_pct > opps[1].net_profit_pct


def test_detect_triangular_raises_on_negative_stablecoin_cost():
    with pytest.raises(ValueError, match="stablecoin_cost"):
        detect_triangular(_binance_kraken_state(), stablecoin_cost=-0.1)


# ── withdrawal cost ──────────────────────────────────────────────────────────────
# BUY leg is Binance @ ask 100000; Binance BTC withdrawal fee = 0.0005 BTC.
# withdrawal_cost = 0.0005 * 100000 = 50.0 (quote units).

def test_detect_triangular_charges_withdrawal_on_buy_venue():
    opp = detect_triangular(_binance_kraken_state(), stablecoin_cost=0.0)[0]

    assert opp.withdrawal_cost == pytest.approx(50.0, rel=1e-9)


def test_detect_triangular_net_profit_subtracts_withdrawal():
    # Default notional 10_000: gross-of-withdrawal = 10000 * 0.001384613 = 13.846,
    # minus the 50.0 fixed withdrawal → net is negative at this small size.
    opp = detect_triangular(_binance_kraken_state(), stablecoin_cost=0.0)[0]

    expected = 10_000.0 * (_HAND_NET_MULTIPLIER - 1.0) - 50.0
    assert opp.net_profit == pytest.approx(expected, rel=1e-6)
    assert opp.net_profit < 0  # fixed withdrawal dominates a thin edge at 10k


def test_detect_triangular_net_profit_turns_positive_at_large_notional():
    opp = detect_triangular(
        _binance_kraken_state(), stablecoin_cost=0.0, notional=1_000_000.0
    )[0]

    expected = 1_000_000.0 * (_HAND_NET_MULTIPLIER - 1.0) - 50.0
    assert opp.net_profit == pytest.approx(expected, rel=1e-6)
    assert opp.net_profit > 0
