from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import duckdb
import pytest

from core.executor import MIN_TRADE_SIZE_BTC, simulate_execution_depth
from models.market import Exchange, OrderBook, OrderBookLevel, Opportunity
from models.trade import WalletBalance

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)
_FRESH = _NOW - timedelta(milliseconds=100)


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


def _levels(*pairs: tuple[float, float]) -> list[OrderBookLevel]:
    return [OrderBookLevel(price=p, qty=q) for p, q in pairs]


def _book(exchange: Exchange, bids, asks, received_at: datetime = _FRESH) -> OrderBook:
    return OrderBook(exchange=exchange, bids=bids, asks=asks, ws_received_at=received_at)


def _opp() -> Opportunity:
    return Opportunity(
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        buy_ask=70_000.0,
        sell_bid=70_500.0,
        gross_spread=250.0,
        net_spread=120.0,
        score=0.001,
        detected_at=_NOW - timedelta(milliseconds=50),
        available_qty=0.5,
        optimal_qty=0.5,
    )


def _wallets(usdt: float = 100_000.0, btc: float = 2.0) -> dict[Exchange, WalletBalance]:
    return {
        Exchange.BINANCE: WalletBalance(exchange=Exchange.BINANCE, usdt=usdt, btc=0.0, updated_at=_NOW),
        Exchange.KRAKEN: WalletBalance(exchange=Exchange.KRAKEN, usdt=0.0, btc=btc, updated_at=_NOW),
    }


def _books(buy_asks, sell_bids) -> dict[Exchange, OrderBook]:
    return {
        Exchange.BINANCE: _book(Exchange.BINANCE, bids=_levels((69_990.0, 5.0)), asks=buy_asks),
        Exchange.KRAKEN: _book(Exchange.KRAKEN, bids=sell_bids, asks=_levels((70_600.0, 5.0))),
    }


# ── full fill across multiple levels ──────────────────────────────────────────

def test_depth_full_fill_walks_both_books_known_answer(mock_db):
    # walk-the-book VWAPs (this module's responsibility — independent of the cost model):
    #   buy:  0.3@70_000 + 0.2@70_010 → avg 70_004.0
    #   sell: 0.4@70_500 + 0.1@70_490 → avg 70_498.0
    # net_profit depends on the fees cost model (withdrawal/latency/slippage live in
    # core/fees.py) — asserted as > 0 here, not pinned to an exact value.
    books = _books(
        buy_asks=_levels((70_000.0, 0.3), (70_010.0, 0.5)),
        sell_bids=_levels((70_500.0, 0.4), (70_490.0, 0.5)),
    )
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    assert trade.status == "EXECUTED"
    assert trade.qty == pytest.approx(0.5)
    assert trade.fill_ratio == pytest.approx(1.0)
    assert trade.buy_price == pytest.approx(70_004.0)
    assert trade.sell_price == pytest.approx(70_498.0)
    assert trade.net_profit > 0


def test_depth_single_level_no_walk(mock_db):
    books = _books(
        buy_asks=_levels((70_000.0, 1.0)),
        sell_bids=_levels((70_500.0, 1.0)),
    )
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    assert trade.buy_price == pytest.approx(70_000.0)
    assert trade.sell_price == pytest.approx(70_500.0)
    assert trade.slippage_est == pytest.approx(0.0)


# ── partial fill ──────────────────────────────────────────────────────────────

def test_depth_partial_fill_when_buy_depth_thin(mock_db):
    # buy depth only 0.2 BTC, sell has plenty → exec 0.2, fill_ratio 0.4
    books = _books(
        buy_asks=_levels((70_000.0, 0.2)),
        sell_bids=_levels((70_500.0, 1.0)),
    )
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    assert trade.status == "EXECUTED"
    assert trade.qty == pytest.approx(0.2)
    assert trade.fill_ratio == pytest.approx(0.4)


def test_depth_partial_fill_limited_by_thinner_leg(mock_db):
    # buy can do 0.5 but sell only 0.15 → exec 0.15
    books = _books(
        buy_asks=_levels((70_000.0, 0.5)),
        sell_bids=_levels((70_500.0, 0.15)),
    )
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    assert trade.qty == pytest.approx(0.15)
    assert trade.fill_ratio == pytest.approx(0.3)


def test_depth_slippage_positive_when_walking(mock_db):
    # walking past best price incurs slippage > 0
    books = _books(
        buy_asks=_levels((70_000.0, 0.3), (70_050.0, 0.5)),
        sell_bids=_levels((70_500.0, 0.3), (70_400.0, 0.5)),
    )
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    assert trade.slippage_est > 0


# ── rejections ────────────────────────────────────────────────────────────────

def test_depth_rejects_below_min_trade_size(mock_db):
    books = _books(_levels((70_000.0, 1.0)), _levels((70_500.0, 1.0)))
    trade = simulate_execution_depth(_opp(), MIN_TRADE_SIZE_BTC - 1e-6, _wallets(), books, now=_NOW)
    assert trade.status == "SKIPPED_MIN_FILL"
    assert trade.fill_ratio == 0.0


def test_depth_rejects_when_matched_qty_below_min(mock_db):
    # both legs nearly empty → exec_qty below min
    tiny = MIN_TRADE_SIZE_BTC / 2
    books = _books(_levels((70_000.0, tiny)), _levels((70_500.0, tiny)))
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    assert trade.status == "SKIPPED_MIN_FILL"


def test_depth_rejects_stale_book(mock_db):
    stale = _NOW - timedelta(milliseconds=600)
    books = {
        Exchange.BINANCE: _book(Exchange.BINANCE, _levels((69_990.0, 5.0)), _levels((70_000.0, 1.0)), received_at=stale),
        Exchange.KRAKEN: _book(Exchange.KRAKEN, _levels((70_500.0, 1.0)), _levels((70_600.0, 5.0))),
    }
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    assert trade.status == "ABORTED_STALE"


def test_depth_rejects_negative_spread_after_walk(mock_db):
    # walking deep makes buy avg exceed sell avg → net <= 0
    books = _books(
        buy_asks=_levels((70_400.0, 0.5)),
        sell_bids=_levels((70_000.0, 0.5)),
    )
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    assert trade.status == "ABORTED_STALE"


def test_depth_rejects_insufficient_usdt(mock_db):
    books = _books(_levels((70_000.0, 1.0)), _levels((70_500.0, 1.0)))
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(usdt=1.0), books, now=_NOW)
    assert trade.status == "REJECTED_INSUFFICIENT_BALANCE"


def test_depth_persists_executed_trade(mock_db):
    books = _books(_levels((70_000.0, 1.0)), _levels((70_500.0, 1.0)))
    trade = simulate_execution_depth(_opp(), 0.5, _wallets(), books, now=_NOW)
    rows = mock_db.execute("SELECT id, status FROM trades").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == trade.id
