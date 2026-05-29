from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.rebalancer import plan_rebalance
from models.market import Exchange
from models.trade import WalletBalance

_NOW = datetime(2026, 5, 29, 6, 0, 0, tzinfo=timezone.utc)
_BTC_PRICE = 100_000.0  # → BTC withdrawal fees: Binance $50, Kraken $15, Gemini $100, Coinbase $10


def _wallet(ex: Exchange, btc: float = 0.0, usdt: float = 0.0) -> WalletBalance:
    return WalletBalance(exchange=ex, usdt=usdt, btc=btc, updated_at=_NOW)


# ── known rebalance (computed by hand) ───────────────────────────────────────────
# Binance 1.5 BTC → target 1.0 (surplus 0.5); Kraken 0.5 → target 1.0 (deficit 0.5).
# One transfer Binance→Kraken of 0.5 BTC; fee = 0.0005·100_000 = $50.

def test_plan_rebalance_known_single_transfer():
    wallets = {
        Exchange.BINANCE: _wallet(Exchange.BINANCE, btc=1.5),
        Exchange.KRAKEN: _wallet(Exchange.KRAKEN, btc=0.5),
    }
    targets = {"BTC": {Exchange.BINANCE: 1.0, Exchange.KRAKEN: 1.0}}

    plan = plan_rebalance(wallets, targets, btc_price=_BTC_PRICE, band=0.0)

    assert plan.status == "OK"
    assert len(plan.transfers) == 1
    t = plan.transfers[0]
    assert t.asset == "BTC"
    assert t.from_exchange == Exchange.BINANCE
    assert t.to_exchange == Exchange.KRAKEN
    assert t.amount == pytest.approx(0.5, abs=1e-6)
    assert t.fee_usd == pytest.approx(50.0, rel=1e-9)
    assert plan.total_cost_usd == pytest.approx(50.0, rel=1e-9)


def test_plan_rebalance_no_action_when_within_band():
    # ±10% band: 1.05 and 0.95 both sit inside [0.9, 1.1] of target 1.0.
    wallets = {
        Exchange.BINANCE: _wallet(Exchange.BINANCE, btc=1.05),
        Exchange.KRAKEN: _wallet(Exchange.KRAKEN, btc=0.95),
    }
    targets = {"BTC": {Exchange.BINANCE: 1.0, Exchange.KRAKEN: 1.0}}

    plan = plan_rebalance(wallets, targets, btc_price=_BTC_PRICE, band=0.10)

    assert plan.status == "BALANCED"
    assert plan.transfers == []
    assert plan.total_cost_usd == 0.0


def test_plan_rebalance_picks_cheapest_source():
    # Coinbase needs ≥0.5 BTC (band 0.5 → min 0.5). Kraken ($15) and Gemini ($100)
    # both sit at max 1.5 and CAN supply, but the min-cost flow uses only Kraken.
    wallets = {
        Exchange.KRAKEN: _wallet(Exchange.KRAKEN, btc=1.5),
        Exchange.GEMINI: _wallet(Exchange.GEMINI, btc=1.5),
        Exchange.COINBASE: _wallet(Exchange.COINBASE, btc=0.0),
    }
    targets = {
        "BTC": {Exchange.KRAKEN: 1.0, Exchange.GEMINI: 1.0, Exchange.COINBASE: 1.0}
    }

    plan = plan_rebalance(wallets, targets, btc_price=_BTC_PRICE, band=0.5)

    assert plan.status == "OK"
    assert len(plan.transfers) == 1
    t = plan.transfers[0]
    assert t.from_exchange == Exchange.KRAKEN  # cheaper than Gemini
    assert t.to_exchange == Exchange.COINBASE
    assert t.amount == pytest.approx(0.5, abs=1e-6)
    assert plan.total_cost_usd == pytest.approx(15.0, rel=1e-9)


def test_plan_rebalance_infeasible_when_totals_mismatch_and_band_zero():
    # Σ current (3.0) ≠ Σ target (2.0); transfers conserve the asset, so with a
    # zero band there is no feasible plan.
    wallets = {
        Exchange.BINANCE: _wallet(Exchange.BINANCE, btc=2.0),
        Exchange.KRAKEN: _wallet(Exchange.KRAKEN, btc=1.0),
    }
    targets = {"BTC": {Exchange.BINANCE: 1.0, Exchange.KRAKEN: 1.0}}

    plan = plan_rebalance(wallets, targets, btc_price=_BTC_PRICE, band=0.0)

    assert plan.status == "INFEASIBLE"
    assert plan.transfers == []


def test_plan_rebalance_usdt_uses_flat_withdrawal_fee():
    wallets = {
        Exchange.BINANCE: _wallet(Exchange.BINANCE, usdt=12_000.0),
        Exchange.KRAKEN: _wallet(Exchange.KRAKEN, usdt=8_000.0),
    }
    targets = {"USDT": {Exchange.BINANCE: 10_000.0, Exchange.KRAKEN: 10_000.0}}

    plan = plan_rebalance(
        wallets, targets, btc_price=_BTC_PRICE, band=0.0, stablecoin_withdrawal_usd=1.0
    )

    assert plan.status == "OK"
    assert len(plan.transfers) == 1
    t = plan.transfers[0]
    assert t.asset == "USDT"
    assert t.from_exchange == Exchange.BINANCE
    assert t.amount == pytest.approx(2_000.0, abs=1e-3)
    assert t.fee_usd == pytest.approx(1.0, rel=1e-9)


def test_plan_rebalance_handles_btc_and_usdt_together():
    wallets = {
        Exchange.BINANCE: _wallet(Exchange.BINANCE, btc=1.5, usdt=12_000.0),
        Exchange.KRAKEN: _wallet(Exchange.KRAKEN, btc=0.5, usdt=8_000.0),
    }
    targets = {
        "BTC": {Exchange.BINANCE: 1.0, Exchange.KRAKEN: 1.0},
        "USDT": {Exchange.BINANCE: 10_000.0, Exchange.KRAKEN: 10_000.0},
    }

    plan = plan_rebalance(wallets, targets, btc_price=_BTC_PRICE, band=0.0)

    assert plan.status == "OK"
    assert len(plan.transfers) == 2
    assert {t.asset for t in plan.transfers} == {"BTC", "USDT"}
    # total = BTC withdrawal ($50) + USDT withdrawal ($1)
    assert plan.total_cost_usd == pytest.approx(51.0, rel=1e-9)
    assert plan.total_cost_usd == pytest.approx(sum(t.fee_usd for t in plan.transfers))


def test_plan_rebalance_raises_on_invalid_btc_price():
    wallets = {Exchange.BINANCE: _wallet(Exchange.BINANCE, btc=1.0)}
    with pytest.raises(ValueError, match="btc_price"):
        plan_rebalance(wallets, {"BTC": {Exchange.BINANCE: 1.0}}, btc_price=0.0)


def test_plan_rebalance_raises_on_negative_band():
    wallets = {Exchange.BINANCE: _wallet(Exchange.BINANCE, btc=1.0)}
    with pytest.raises(ValueError, match="band"):
        plan_rebalance(wallets, {"BTC": {Exchange.BINANCE: 1.0}}, btc_price=_BTC_PRICE, band=-0.1)
