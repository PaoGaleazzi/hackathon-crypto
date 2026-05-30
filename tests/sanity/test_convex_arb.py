from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.convex_arb import arbitrage_to_dict, solve_arbitrage
from core.fees import OrderSide, get_fee_rate
from models.market import BBO, Exchange, OrderBook, OrderBookLevel

_NOW = datetime(2026, 5, 30, 6, 0, 0, tzinfo=timezone.utc)


def _bbo(exchange: Exchange, bid: float, ask: float, qty: float = 1.0) -> BBO:
    return BBO(
        exchange=exchange,
        bid=bid,
        ask=ask,
        bid_qty=qty,
        ask_qty=qty,
        ws_received_at=_NOW,
    )


def _ob(exchange: Exchange, asks, bids) -> OrderBook:
    return OrderBook(
        exchange=exchange,
        ws_received_at=_NOW,
        asks=[OrderBookLevel(price=p, qty=q) for p, q in asks],
        bids=[OrderBookLevel(price=p, qty=q) for p, q in bids],
    )


# ── known-answer: cross-quote spatial arb (Binance USDT vs Kraken USD) ────────────
#
# Buy 1 BTC on Binance @ ask 100000 (taker 0.001) → credited 0.999 BTC.
# Sell those 0.999 BTC on Kraken @ bid 100500 (taker 0.0026) → 0.999·100500·0.9974
#   = 100138.46 USD. Convert USD→USDT back to repay the 100000 USDT outlay.
# With a frictionless stablecoin the surplus cash is exactly the triangular
# hand-calc: 100000·(0.999·0.9974·1.005 − 1) = 138.4613 USD.
_HAND_PROFIT = 100_000.0 * (0.999 * 0.9974 * 1.005 - 1.0)  # == 138.4613...


def _binance_kraken_state() -> dict[Exchange, BBO]:
    return {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=100_500.0, ask=100_510.0),
    }


def test_obvious_arbitrage_detected_with_correct_quantities():
    result = solve_arbitrage(_binance_kraken_state(), stablecoin_cost=0.0)

    assert result.is_arbitrage is True
    assert result.profit_usd == pytest.approx(_HAND_PROFIT, rel=1e-6)
    assert "arbitrage exists" in result.certificate

    active = result.active_trades
    assert set(active) == {Exchange.BINANCE, Exchange.KRAKEN}
    assert active[Exchange.BINANCE].side == "BUY"
    assert active[Exchange.KRAKEN].side == "SELL"
    # Buy 1 BTC on Binance (full top-of-book), the 0.999 credited get sold on Kraken.
    assert active[Exchange.BINANCE].buy_btc == pytest.approx(1.0, rel=1e-6)
    assert active[Exchange.KRAKEN].sell_btc == pytest.approx(0.999, rel=1e-6)


def test_no_arbitrage_is_certified_as_zero():
    # Kraken now strictly below Binance — no profitable cross.
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=99_980.0, ask=99_995.0),
    }
    result = solve_arbitrage(state, stablecoin_cost=0.0)

    assert result.is_arbitrage is False
    assert result.profit_usd == pytest.approx(0.0, abs=1e-6)
    assert result.certificate == "no arbitrage exists (convex optimum = 0)"
    # Nothing to execute when the optimum is zero.
    assert result.active_trades == {}


def test_single_venue_never_arbitrages_against_itself():
    # One book: ask > bid by construction, so no self-arbitrage can exist.
    state = {Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=100_000.0, ask=100_010.0)}
    result = solve_arbitrage(state)

    assert result.is_arbitrage is False
    assert result.profit_usd == pytest.approx(0.0, abs=1e-6)


# ── triangular USD→BTC→USDT→USD with known numbers ───────────────────────────────
#
# Hold USD. Buy BTC on Kraken (USD), sell BTC on Binance (USDT), convert USDT→USD.
#   buy  1 BTC @ Kraken ask 100000, taker 0.0026 → 0.9974 BTC credited
#   sell 0.9974 BTC @ Binance bid 100500, taker 0.001 → 0.9974·100500·0.999 USDT
#   convert USDT→USD at par (cost 0) → same USD
# net multiplier per USD = 0.9974/100000 · (100500·0.999) · 1 ... settle in USD.
def test_triangular_usd_btc_usdt_cycle_known_numbers():
    state = {
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=99_990.0, ask=100_000.0),
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=100_500.0, ask=100_510.0),
    }
    expected = 100_000.0 * (0.9974 * 0.999 * 1.005 - 1.0)  # buy Kraken, sell Binance

    result = solve_arbitrage(state, stablecoin_cost=0.0)

    assert result.is_arbitrage is True
    assert result.profit_usd == pytest.approx(expected, rel=1e-6)
    assert result.active_trades[Exchange.KRAKEN].side == "BUY"
    assert result.active_trades[Exchange.BINANCE].side == "SELL"


def test_respects_order_book_liquidity_limits():
    # Binance top ask only 0.4 BTC of cheap liquidity; the next level (100600) is
    # above Kraken's bid 100500, so it is unprofitable. The optimum must stop at
    # the 0.4 BTC available, never invent liquidity.
    state = _binance_kraken_state()
    depth = {
        Exchange.BINANCE: _ob(
            Exchange.BINANCE,
            asks=[(100_000.0, 0.4), (100_600.0, 10.0)],
            bids=[(99_990.0, 5.0)],
        ),
        Exchange.KRAKEN: _ob(
            Exchange.KRAKEN,
            asks=[(100_510.0, 5.0)],
            bids=[(100_500.0, 5.0), (100_400.0, 5.0)],
        ),
    }
    result = solve_arbitrage(state, depth=depth, stablecoin_cost=0.0)

    assert result.is_arbitrage is True
    # Bought exactly the cheap 0.4 BTC tranche, nothing from the unprofitable level.
    assert result.active_trades[Exchange.BINANCE].buy_btc == pytest.approx(0.4, rel=1e-6)
    assert result.active_trades[Exchange.KRAKEN].sell_btc == pytest.approx(
        0.4 * 0.999, rel=1e-6
    )


def test_deeper_book_lets_optimum_size_up():
    # Same prices, but now 3 BTC of cheap Binance liquidity all below Kraken's bid.
    state = _binance_kraken_state()
    depth = {
        Exchange.BINANCE: _ob(
            Exchange.BINANCE, asks=[(100_000.0, 3.0)], bids=[(99_990.0, 5.0)]
        ),
        Exchange.KRAKEN: _ob(
            Exchange.KRAKEN, asks=[(100_510.0, 5.0)], bids=[(100_500.0, 5.0)]
        ),
    }
    result = solve_arbitrage(state, depth=depth, stablecoin_cost=0.0)

    # 3× the size of the 1-BTC BBO case → ~3× the profit.
    assert result.active_trades[Exchange.BINANCE].buy_btc == pytest.approx(3.0, rel=1e-6)
    assert result.profit_usd == pytest.approx(3.0 * _HAND_PROFIT, rel=1e-6)


def test_fees_reduce_profit():
    state = _binance_kraken_state()
    zero_fees = {Exchange.BINANCE: 0.0, Exchange.KRAKEN: 0.0}

    with_fees = solve_arbitrage(state, stablecoin_cost=0.0)
    without_fees = solve_arbitrage(state, fees=zero_fees, stablecoin_cost=0.0)

    assert without_fees.profit_usd > with_fees.profit_usd
    # Zero-fee gross edge is exactly the raw spread on 1 BTC: 100500 − 100000.
    assert without_fees.profit_usd == pytest.approx(500.0, rel=1e-6)


def test_stablecoin_cost_reduces_cross_quote_profit():
    state = _binance_kraken_state()

    free = solve_arbitrage(state, stablecoin_cost=0.0)
    costly = solve_arbitrage(state, stablecoin_cost=0.001)  # 10 bps conversion

    assert costly.profit_usd < free.profit_usd
    assert costly.is_arbitrage is True


def test_multiple_exchanges_routes_to_best_pair():
    # Coinbase's bid clears its steep 0.6% taker fee — it is the unique best sell,
    # capped at 1 BTC of bid depth. Binance is the cheapest buy with ample depth to
    # supply the whole leg alone, so the dearer OKX/Bybit asks stay untouched.
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0, qty=2.0),
        Exchange.OKX: _bbo(Exchange.OKX, bid=100_040.0, ask=100_050.0),
        Exchange.BYBIT: _bbo(Exchange.BYBIT, bid=100_080.0, ask=100_090.0),
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, bid=100_300.0, ask=100_310.0),
        Exchange.COINBASE: _bbo(Exchange.COINBASE, bid=101_500.0, ask=101_510.0, qty=1.0),
    }
    result = solve_arbitrage(state, stablecoin_cost=0.0)

    assert result.is_arbitrage is True
    active = result.active_trades
    # Cheapest ask is bought, richest bid is sold.
    assert active[Exchange.BINANCE].side == "BUY"
    assert active[Exchange.COINBASE].side == "SELL"
    # Binance alone supplies the whole BTC leg, so the dearer venues are unused.
    assert Exchange.OKX not in active
    assert Exchange.BYBIT not in active


def test_same_quote_arbitrage_without_conversion():
    # Both USDT venues — no USD↔USDT conversion needed, pure spatial within USDT.
    state = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, bid=99_990.0, ask=100_000.0),
        Exchange.OKX: _bbo(Exchange.OKX, bid=100_500.0, ask=100_510.0),
    }
    result = solve_arbitrage(state)

    assert result.is_arbitrage is True
    assert result.conversions == {}  # never touched the stablecoin market
    assert result.active_trades[Exchange.BINANCE].side == "BUY"
    assert result.active_trades[Exchange.OKX].side == "SELL"


def test_btc_is_conserved_end_in_cash():
    result = solve_arbitrage(_binance_kraken_state(), stablecoin_cost=0.0)

    total_net_btc = sum(t.net_btc for t in result.trades_per_exchange.values())
    assert total_net_btc == pytest.approx(0.0, abs=1e-6)


def test_default_fees_match_live_schedule():
    # Not overriding fees must use the real taker schedule from core.fees.
    state = _binance_kraken_state()
    explicit = {
        Exchange.BINANCE: get_fee_rate(Exchange.BINANCE, OrderSide.TAKER),
        Exchange.KRAKEN: get_fee_rate(Exchange.KRAKEN, OrderSide.TAKER),
    }
    default_run = solve_arbitrage(state, stablecoin_cost=0.0)
    explicit_run = solve_arbitrage(state, fees=explicit, stablecoin_cost=0.0)

    assert default_run.profit_usd == pytest.approx(explicit_run.profit_usd, rel=1e-9)


def test_empty_state_is_no_arbitrage():
    result = solve_arbitrage({})

    assert result.is_arbitrage is False
    assert result.profit_usd == 0.0
    assert result.trades_per_exchange == {}


def test_arbitrage_to_dict_is_json_shaped():
    result = solve_arbitrage(_binance_kraken_state(), stablecoin_cost=0.0)
    payload = arbitrage_to_dict(result)

    assert payload["is_arbitrage"] is True
    assert payload["profit_usd"] == pytest.approx(_HAND_PROFIT, rel=1e-6)
    assert {t["exchange"] for t in payload["trades"]} == {"binance", "kraken"}
    sides = {t["exchange"]: t["side"] for t in payload["trades"]}
    assert sides == {"binance": "BUY", "kraken": "SELL"}


def test_negative_stablecoin_cost_rejected():
    with pytest.raises(ValueError, match="stablecoin_cost"):
        solve_arbitrage(_binance_kraken_state(), stablecoin_cost=-0.01)
