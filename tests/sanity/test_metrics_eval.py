from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.metrics_eval import evaluate_run, percentile
from models.market import Exchange
from models.trade import Trade, TradeStatus

_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)


def _trade(status: TradeStatus, net_profit: float, latency_ms: float) -> Trade:
    return Trade(
        id="x",
        buy_exchange=Exchange.BINANCE,
        sell_exchange=Exchange.KRAKEN,
        qty=0.1,
        buy_price=70_000.0,
        sell_price=70_100.0,
        fee_buy=1.0,
        fee_sell=1.0,
        slippage_est=0.0,
        net_profit=net_profit,
        status=status,
        ws_received_at=_NOW,
        decision_at=_NOW,
        latency_ms=latency_ms,
        executed_at=_NOW,
    )


# ── percentile ────────────────────────────────────────────────────────────────


def test_percentile_empty_is_zero():
    assert percentile([], 50.0) == 0.0


def test_percentile_single_value():
    assert percentile([42.0], 95.0) == 42.0


def test_percentile_median_and_p95_linear_interp():
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(values, 50.0) == 3.0
    # rank = 0.95 * 4 = 3.8 → 4.0 + 0.8*(5.0-4.0) = 4.8
    assert percentile(values, 95.0) == pytest.approx(4.8)


def test_percentile_rejects_out_of_range():
    with pytest.raises(ValueError):
        percentile([1.0], 150.0)


# ── evaluate_run ──────────────────────────────────────────────────────────────


def test_evaluate_empty_run():
    m = evaluate_run([], label="empty")
    assert m.n_trades == 0
    assert m.trades_executed == 0
    assert m.precision == 0.0
    assert m.pnl_simulated == 0.0
    assert m.latency_p50_ms == 0.0


def test_evaluate_classifies_and_aggregates():
    trades = [
        _trade("EXECUTED", 100.0, 1.0),    # TP
        _trade("EXECUTED", 50.0, 2.0),     # TP
        _trade("EXECUTED", -10.0, 3.0),    # FP (slipped through, unprofitable)
        _trade("ABORTED_STALE", 0.0, 4.0),         # filtered
        _trade("REJECTED_LATENCY_RISK", 0.0, 5.0), # filtered
    ]
    m = evaluate_run(trades, label="mix")

    assert m.label == "mix"
    assert m.n_trades == 5
    assert m.trades_executed == 3
    assert m.true_positives == 2
    assert m.false_positives == 1
    assert m.false_positives_filtered == 2
    assert m.precision == pytest.approx(2 / 3)
    assert m.pnl_simulated == pytest.approx(140.0)  # 100 + 50 - 10
    # latency over ALL decisions: [1,2,3,4,5]
    assert m.latency_p50_ms == pytest.approx(3.0)


def test_precision_is_one_when_all_executed_profitable():
    trades = [_trade("EXECUTED", 10.0, 1.0), _trade("EXECUTED", 20.0, 1.0)]
    m = evaluate_run(trades)
    assert m.precision == 1.0
    assert m.false_positives == 0


def test_to_dict_round_trips_fields():
    m = evaluate_run([_trade("EXECUTED", 10.0, 1.0)], label="d")
    d = m.to_dict()
    assert d["label"] == "d"
    assert d["trades_executed"] == 1
    assert d["pnl_simulated"] == pytest.approx(10.0)
