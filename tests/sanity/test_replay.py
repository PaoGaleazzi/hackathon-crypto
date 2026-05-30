from __future__ import annotations

from datetime import datetime, timedelta, timezone

import core.fees as fees_module
from core.replay import (
    ReplayStats,
    RunConfig,
    TickRecorder,
    load_ticks,
    record_ticks,
    replay_ticks,
    run_replay,
)
from models.market import BBO, Exchange

_T0 = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)


def _cfg(**kw) -> RunConfig:
    """A funded config so the wallet isn't the binding constraint in tests
    (one BTC trade is ~$70k, far above the 10k default wallet)."""
    kw.setdefault("name", "t")
    kw.setdefault("initial_usdt", 1_000_000.0)
    kw.setdefault("initial_btc", 20.0)
    return RunConfig(**kw)


def _bbo(
    exchange: Exchange,
    bid: float,
    ask: float,
    i: int,
    bid_qty: float = 1.0,
    ask_qty: float = 1.0,
    parse_ms: float = 5.0,
) -> BBO:
    ws = _T0 + timedelta(milliseconds=i * 100)
    return BBO(
        exchange=exchange,
        bid=bid,
        ask=ask,
        bid_qty=bid_qty,
        ask_qty=ask_qty,
        ws_received_at=ws,
        normalized_at=ws + timedelta(milliseconds=parse_ms),
    )


def _arb_dataset(n_pairs: int = 6) -> list[BBO]:
    """Alternating Binance(cheap)/OKX(rich) ticks with a persistent ~500 USD/BTC
    dislocation — wide enough to clear taker fees on both venues (0.1% each)."""
    ticks: list[BBO] = []
    for i in range(n_pairs):
        if i % 2 == 0:
            ticks.append(_bbo(Exchange.BINANCE, bid=69_499.0, ask=69_500.0, i=i))
        else:
            ticks.append(_bbo(Exchange.OKX, bid=70_000.0, ask=70_001.0, i=i))
    return ticks


# ── recording round-trip ──────────────────────────────────────────────────────


def test_record_and_replay_round_trip(tmp_path):
    path = tmp_path / "ticks.jsonl"
    original = _arb_dataset(4)
    n = record_ticks(original, path)
    assert n == 4

    loaded = load_ticks(path)
    assert loaded == original  # frozen BBOs compare by value — lossless round-trip


def test_replay_preserves_order_and_is_a_generator(tmp_path):
    path = tmp_path / "ticks.jsonl"
    original = _arb_dataset(6)
    record_ticks(original, path)

    streamed = list(replay_ticks(path))
    assert [b.exchange for b in streamed] == [b.exchange for b in original]


def test_recorder_appends_across_sessions(tmp_path):
    path = tmp_path / "ticks.jsonl"
    with TickRecorder(path) as rec:
        rec.record(_bbo(Exchange.BINANCE, 1.0, 2.0, 0))
    with TickRecorder(path) as rec:
        rec.record(_bbo(Exchange.OKX, 1.0, 2.0, 1))
    assert len(load_ticks(path)) == 2


def test_blank_lines_are_skipped(tmp_path):
    path = tmp_path / "ticks.jsonl"
    record_ticks(_arb_dataset(2), path)
    with path.open("a") as fh:
        fh.write("\n\n")
    assert len(load_ticks(path)) == 2


# ── backtest engine ────────────────────────────────────────────────────────────


def test_run_replay_executes_profitable_arbs():
    trades = run_replay(_arb_dataset(6), _cfg())
    executed = [t for t in trades if t.status == "EXECUTED"]
    assert executed, "a clear cross-venue arb should produce executed trades"
    assert all(t.net_profit > 0 for t in executed)


def test_run_replay_is_deterministic():
    ticks = _arb_dataset(8)
    cfg = _cfg()
    a = run_replay(ticks, cfg)
    b = run_replay(ticks, cfg)
    assert [(t.status, t.net_profit, t.qty) for t in a] == [
        (t.status, t.net_profit, t.qty) for t in b
    ]


def test_run_replay_does_not_mutate_input_ticks():
    ticks = _arb_dataset(6)
    snapshot = list(ticks)
    run_replay(ticks, _cfg())
    assert ticks == snapshot


def test_latency_ms_reflects_recorded_parse_latency():
    ticks = _arb_dataset(6)  # parse_ms=5.0 on every tick
    executed = [t for t in run_replay(ticks, _cfg()) if t.status == "EXECUTED"]
    assert executed
    assert all(abs(t.latency_ms - 5.0) < 1e-6 for t in executed)


def test_min_net_spread_floor_suppresses_trades():
    ticks = _arb_dataset(8)
    open_run = run_replay(ticks, _cfg(name="open", min_net_spread_usd=0.0))
    strict = run_replay(ticks, _cfg(name="strict", min_net_spread_usd=1e9))
    n_open = sum(1 for t in open_run if t.status == "EXECUTED")
    n_strict = sum(1 for t in strict if t.status == "EXECUTED")
    assert n_open > 0
    assert n_strict == 0


def test_enable_microprice_toggle_runs_and_is_deterministic():
    ticks = _arb_dataset(8)
    on = run_replay(ticks, _cfg(enable_microprice=True))
    off = run_replay(ticks, _cfg(enable_microprice=False))
    # Both produce valid, profitable executed trades regardless of the toggle.
    for run in (on, off):
        executed = [t for t in run if t.status == "EXECUTED"]
        assert executed
        assert all(t.net_profit > 0 for t in executed)
    # Disabling the signal is deterministic across runs.
    again = run_replay(ticks, _cfg(enable_microprice=False))
    assert [t.net_profit for t in off] == [t.net_profit for t in again]


def test_run_replay_collects_funnel_stats():
    ticks = _arb_dataset(8)
    stats = ReplayStats()
    trades = run_replay(ticks, _cfg(), stats=stats)
    executed = [t for t in trades if t.status == "EXECUTED"]
    # The funnel is internally consistent with the returned trades.
    assert stats.ticks == len(ticks)
    assert stats.state_ready <= stats.ticks
    assert stats.executed == len(executed)
    assert stats.opportunities_detected >= stats.passed_min_spread >= stats.sized_ok
    assert "EXECUTED" in stats.funnel()


def test_fee_multiplier_zero_beats_full_fees_on_pnl():
    ticks = _arb_dataset(8)
    full = run_replay(ticks, _cfg(fee_multiplier=1.0))
    free = run_replay(ticks, _cfg(fee_multiplier=0.0))
    pnl_full = sum(t.net_profit for t in full if t.status == "EXECUTED")
    pnl_free = sum(t.net_profit for t in free if t.status == "EXECUTED")
    # Removing fees cannot lower per-trade profit.
    assert pnl_free >= pnl_full


def test_cost_model_override_restores_fee_tables():
    fees_before = fees_module._FEE_RATES
    wd_before = fees_module._WITHDRAWAL_FEES_BTC
    run_replay(_arb_dataset(4), _cfg(fee_multiplier=0.25, include_withdrawal=False))
    # The module-level tables are the very same objects after the run.
    assert fees_module._FEE_RATES is fees_before
    assert fees_module._WITHDRAWAL_FEES_BTC is wd_before


def test_default_run_replay_does_not_touch_fee_tables():
    # fee_multiplier=1.0 + include_withdrawal=True is a no-op: identity preserved.
    fees_before = fees_module._FEE_RATES
    run_replay(_arb_dataset(4), _cfg())
    assert fees_module._FEE_RATES is fees_before


def test_settings_override_is_restored_after_run():
    from config import settings

    before = (settings.stale_quote_ms, settings.min_fill_ratio)
    run_replay(
        _arb_dataset(4),
        _cfg(stale_quote_ms=123, min_fill_ratio=0.99),
    )
    assert (settings.stale_quote_ms, settings.min_fill_ratio) == before
