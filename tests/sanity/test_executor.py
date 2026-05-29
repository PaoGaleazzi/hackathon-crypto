from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import duckdb
import pytest

from core.executor import MIN_TRADE_SIZE_BTC, simulate_execution
from models.market import BBO, Exchange, Opportunity
from models.trade import WalletBalance

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)
_FRESH = _NOW - timedelta(milliseconds=100)   # 100ms old — within 500ms threshold
_STALE = _NOW - timedelta(milliseconds=600)   # 600ms old — beyond threshold


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE trades (
            id VARCHAR PRIMARY KEY, opportunity_id VARCHAR,
            buy_exchange VARCHAR NOT NULL, sell_exchange VARCHAR NOT NULL,
            qty DOUBLE NOT NULL, buy_price DOUBLE NOT NULL, sell_price DOUBLE NOT NULL,
            fee_buy DOUBLE NOT NULL, fee_sell DOUBLE NOT NULL,
            slippage_est DOUBLE NOT NULL, net_profit DOUBLE NOT NULL,
            status VARCHAR NOT NULL, ws_received_at TIMESTAMPTZ NOT NULL,
            decision_at TIMESTAMPTZ NOT NULL, latency_ms DOUBLE NOT NULL,
            executed_at TIMESTAMPTZ NOT NULL
        )
    """)
    with patch("core.executor.get_connection", return_value=conn):
        yield conn


def _opp(
    buy_ask: float = 70_000.0,
    sell_bid: float = 70_500.0,
) -> Opportunity:
    return Opportunity(
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        buy_ask=buy_ask,
        sell_bid=sell_bid,
        gross_spread=(sell_bid - buy_ask) * 0.5,
        net_spread=123.35,
        score=0.001,
        detected_at=_NOW - timedelta(milliseconds=50),
        available_qty=0.5,
        optimal_qty=0.5,
    )


def _bbo(exchange: Exchange, ask: float, bid: float, received_at: datetime = _FRESH) -> BBO:
    return BBO(
        exchange=exchange, bid=bid, ask=ask,
        bid_qty=2.0, ask_qty=2.0, ws_received_at=received_at,
    )


def _wallets(usdt: float = 100_000.0, btc: float = 2.0) -> dict[Exchange, WalletBalance]:
    return {
        Exchange.BINANCE: WalletBalance(
            exchange=Exchange.BINANCE, usdt=usdt, btc=0.0, updated_at=_NOW,
        ),
        Exchange.KRAKEN: WalletBalance(
            exchange=Exchange.KRAKEN, usdt=0.0, btc=btc, updated_at=_NOW,
        ),
    }


def _current_bbo(buy_ask: float = 70_000.0, sell_bid: float = 70_500.0) -> dict[Exchange, BBO]:
    return {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, ask=buy_ask, bid=buy_ask - 10),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  ask=sell_bid + 10, bid=sell_bid),
    }


# ── successful execution ──────────────────────────────────────────────────────

def test_execute_returns_executed_status(mock_db):
    trade = simulate_execution(_opp(), 0.5, _wallets(), _current_bbo(), now=_NOW)
    assert trade.status == "EXECUTED"


def test_execute_net_profit_known_answer(mock_db):
    # buy BINANCE ask=70_000, sell KRAKEN bid=70_500, qty=0.5; BBO ask_qty=bid_qty=2.0
    # gross        = (70_500 - 70_000) * 0.5                              = 250.0
    # fee_buy      = 0.5 * 70_000 * 0.001                                 =  35.0
    # fee_sell     = 0.5 * 70_500 * 0.0026                                =  91.65
    # withdrawal   = 0.0005 * 70_000                                       =  35.0
    # slippage_buy = 0.001 * sqrt(0.5/2.0) * 0.5 * 70_000                =  17.5
    # slippage_sell= 0.001 * sqrt(0.5/2.0) * 0.5 * 70_500                =  17.625
    # latency_buy  ≈ 0.5 * 70_000 * vol_per_ms * 5ms                     ≈   0.789
    # latency_sell ≈ 0.5 * 70_500 * vol_per_ms * 50ms                    ≈   7.940
    # net ≈ 250 - 35 - 91.65 - 35 - 17.5 - 17.625 - 0.789 - 7.940      ≈  44.50
    trade = simulate_execution(_opp(), 0.5, _wallets(), _current_bbo(), now=_NOW)
    assert trade.net_profit == pytest.approx(44.496725529006646, rel=1e-4)


def test_execute_updates_buy_wallet(mock_db):
    # cost_usdt = 70_000 * 0.5 + fee_buy(35.0) + withdrawal(35.0) = 35_070.0
    # wallet_buy.usdt after = 100_000 - 35_070 = 64_930
    # wallet_buy.btc after  = 0 + 0.5 = 0.5
    wallets = _wallets()
    simulate_execution(_opp(), 0.5, wallets, _current_bbo(), now=_NOW)
    assert wallets[Exchange.BINANCE].usdt == pytest.approx(64_930.0)
    assert wallets[Exchange.BINANCE].btc == pytest.approx(0.5)


def test_execute_updates_sell_wallet(mock_db):
    # wallet_sell.btc after  = 2.0 - 0.5 = 1.5
    # wallet_sell.usdt after = 70_500 * 0.5 - fee_sell(91.65) = 35_158.35
    wallets = _wallets()
    simulate_execution(_opp(), 0.5, wallets, _current_bbo(), now=_NOW)
    assert wallets[Exchange.KRAKEN].btc == pytest.approx(1.5)
    assert wallets[Exchange.KRAKEN].usdt == pytest.approx(35_158.35)


def test_execute_persists_to_db(mock_db):
    trade = simulate_execution(_opp(), 0.5, _wallets(), _current_bbo(), now=_NOW)
    rows = mock_db.execute("SELECT id, status FROM trades").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == trade.id
    assert rows[0][1] == "EXECUTED"


# ── rejection cases ───────────────────────────────────────────────────────────

def test_reject_qty_below_min_trade_size():
    trade = simulate_execution(_opp(), MIN_TRADE_SIZE_BTC - 1e-6, _wallets(), _current_bbo(), now=_NOW)
    assert trade.status == "SKIPPED_MIN_FILL"


def test_reject_stale_buy_quote():
    bbo = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, ask=70_000.0, bid=69_990.0, received_at=_STALE),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  ask=70_510.0, bid=70_500.0, received_at=_FRESH),
    }
    trade = simulate_execution(_opp(), 0.5, _wallets(), bbo, now=_NOW)
    assert trade.status == "ABORTED_STALE"


def test_reject_stale_sell_quote():
    bbo = {
        Exchange.BINANCE: _bbo(Exchange.BINANCE, ask=70_000.0, bid=69_990.0, received_at=_FRESH),
        Exchange.KRAKEN:  _bbo(Exchange.KRAKEN,  ask=70_510.0, bid=70_500.0, received_at=_STALE),
    }
    trade = simulate_execution(_opp(), 0.5, _wallets(), bbo, now=_NOW)
    assert trade.status == "ABORTED_STALE"


def test_reject_spread_turned_negative():
    # Prices moved: buy_ask=70_500, sell_bid=70_000 → spread gone → ABORTED_STALE
    bbo = _current_bbo(buy_ask=70_500.0, sell_bid=70_000.0)
    trade = simulate_execution(_opp(), 0.5, _wallets(), bbo, now=_NOW)
    assert trade.status == "ABORTED_STALE"


def test_reject_insufficient_usdt():
    wallets = _wallets(usdt=1.0)  # need ~35_035, only have 1
    trade = simulate_execution(_opp(), 0.5, wallets, _current_bbo(), now=_NOW)
    assert trade.status == "REJECTED_INSUFFICIENT_BALANCE"


def test_reject_insufficient_btc():
    wallets = _wallets(btc=0.1)  # need 0.5 BTC, only have 0.1
    trade = simulate_execution(_opp(), 0.5, wallets, _current_bbo(), now=_NOW)
    assert trade.status == "REJECTED_INSUFFICIENT_BALANCE"


def test_rejected_trade_does_not_mutate_wallets():
    wallets = _wallets(usdt=1.0)
    original_usdt = wallets[Exchange.BINANCE].usdt
    simulate_execution(_opp(), 0.5, wallets, _current_bbo(), now=_NOW)
    assert wallets[Exchange.BINANCE].usdt == original_usdt


def test_reject_fill_ratio_too_thin():
    # ask_qty=0.1 BTC, qty=0.5 → min(0.1, 2.0)=0.1 < 0.5*0.3=0.15 → SKIPPED_MIN_FILL
    thin_buy_bbo = BBO(
        exchange=Exchange.BINANCE,
        bid=69_990.0, ask=70_000.0,
        bid_qty=2.0, ask_qty=0.1,
        ws_received_at=_FRESH,
    )
    bbo = {
        Exchange.BINANCE: thin_buy_bbo,
        Exchange.KRAKEN: _bbo(Exchange.KRAKEN, ask=70_510.0, bid=70_500.0),
    }
    trade = simulate_execution(_opp(), 0.5, _wallets(), bbo, now=_NOW)
    assert trade.status == "SKIPPED_MIN_FILL"
