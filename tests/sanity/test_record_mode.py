from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest

from core.replay import TickRecorder, load_ticks
from data import bbo_state
from models.market import BBO, Exchange

_NOW = datetime(2026, 5, 29, 12, 0, 0, tzinfo=timezone.utc)


def _bbo(exchange: Exchange, ask: float) -> BBO:
    return BBO(
        exchange=exchange,
        bid=ask - 1.0,
        ask=ask,
        bid_qty=1.0,
        ask_qty=1.0,
        ws_received_at=_NOW,
        normalized_at=_NOW,
    )


# ── RECORD_MODE: bbo_state listener tees every update to the recorder ──────────


@pytest.fixture
def clean_listener():
    """Ensure the global BBO listener is cleared after the test, win or lose."""
    yield
    bbo_state.set_update_listener(None)


def test_listener_receives_every_update(clean_listener):
    captured: list[BBO] = []
    bbo_state.set_update_listener(captured.append)

    bbo_state.update(_bbo(Exchange.BINANCE, 70_000.0))
    bbo_state.update(_bbo(Exchange.OKX, 70_010.0))

    assert [b.exchange for b in captured] == [Exchange.BINANCE, Exchange.OKX]


def test_no_listener_after_clear(clean_listener):
    captured: list[BBO] = []
    bbo_state.set_update_listener(captured.append)
    bbo_state.update(_bbo(Exchange.BINANCE, 70_000.0))
    bbo_state.set_update_listener(None)
    bbo_state.update(_bbo(Exchange.OKX, 70_010.0))
    assert [b.exchange for b in captured] == [Exchange.BINANCE]


def test_record_mode_roundtrip_through_listener(clean_listener, tmp_path):
    """End-to-end: TickRecorder as the bbo_state listener, then replay the file."""
    path = tmp_path / "market_data.jsonl"
    recorder = TickRecorder(path)
    bbo_state.set_update_listener(recorder.record)
    try:
        bbo_state.update(_bbo(Exchange.BINANCE, 70_000.0))
        bbo_state.update(_bbo(Exchange.OKX, 70_010.0))
    finally:
        bbo_state.set_update_listener(None)
        recorder.close()

    loaded = load_ticks(path)
    assert [b.exchange for b in loaded] == [Exchange.BINANCE, Exchange.OKX]
    assert loaded[1].ask == 70_010.0


# ── ab_test.py CLI config overrides ───────────────────────────────────────────


def _load_ab_test():
    ab_path = Path(__file__).resolve().parents[2] / "scripts" / "ab_test.py"
    spec = importlib.util.spec_from_file_location("ab_test", ab_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_make_config_parses_enable_microprice():
    ab = _load_ab_test()
    a = ab.make_config("A", ["enable_microprice=false"])
    b = ab.make_config("B", ["enable_microprice=true"])
    assert a.enable_microprice is False
    assert b.enable_microprice is True
    assert a.name.startswith("A:")
    assert b.name.startswith("B:")


def test_make_config_coerces_types():
    ab = _load_ab_test()
    cfg = ab.make_config(
        "A",
        ["min_net_spread_usd=5", "vol_window=10", "apply_latency_buffer=no",
         "stale_quote_ms=none"],
    )
    assert cfg.min_net_spread_usd == 5.0 and isinstance(cfg.min_net_spread_usd, float)
    assert cfg.vol_window == 10 and isinstance(cfg.vol_window, int)
    assert cfg.apply_latency_buffer is False
    assert cfg.stale_quote_ms is None


def test_make_config_coerces_cost_model_knobs():
    ab = _load_ab_test()
    cfg = ab.make_config("B", ["fee_multiplier=0.5", "include_withdrawal=false"])
    assert cfg.fee_multiplier == 0.5
    assert cfg.include_withdrawal is False


def test_make_config_rejects_unknown_knob():
    ab = _load_ab_test()
    with pytest.raises(SystemExit):
        ab.make_config("A", ["nonsense=1"])


def test_make_config_rejects_malformed_override():
    ab = _load_ab_test()
    with pytest.raises(SystemExit):
        ab.make_config("A", ["enable_microprice"])  # no '='


def test_make_config_empty_overrides_uses_plain_letter():
    ab = _load_ab_test()
    cfg = ab.make_config("A", [])
    assert cfg.name == "A"
