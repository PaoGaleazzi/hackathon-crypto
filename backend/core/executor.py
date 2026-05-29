from __future__ import annotations

import uuid
from datetime import datetime, timezone

from config import settings
from core.fees import OrderSide, calculate_fee, calculate_net_spread
from db.connection import get_connection
from models.market import BBO, Exchange, Opportunity
from models.trade import Trade, TradeStatus, WalletBalance

MIN_TRADE_SIZE_BTC = settings.min_trade_size_btc  # centralized in config.settings


def simulate_execution(
    opportunity: Opportunity,
    qty: float,
    wallets: dict[Exchange, WalletBalance],
    current_bbo: dict[Exchange, BBO],
    now: datetime | None = None,
) -> Trade:
    _now = now if now is not None else datetime.now(timezone.utc)
    buy_ex = opportunity.buy_exchange
    sell_ex = opportunity.sell_exchange

    if qty < MIN_TRADE_SIZE_BTC:
        return _build_rejected(opportunity, qty, _now, "SKIPPED_MIN_FILL")

    bbo_buy = current_bbo.get(buy_ex)
    bbo_sell = current_bbo.get(sell_ex)
    if bbo_buy is None or bbo_sell is None:
        return _build_rejected(opportunity, qty, _now, "ABORTED_STALE")

    buy_age_ms = (_now - bbo_buy.ws_received_at).total_seconds() * 1000
    sell_age_ms = (_now - bbo_sell.ws_received_at).total_seconds() * 1000
    if buy_age_ms > settings.stale_quote_ms or sell_age_ms > settings.stale_quote_ms:
        return _build_rejected(opportunity, qty, _now, "ABORTED_STALE")

    buy_price = bbo_buy.ask
    sell_price = bbo_sell.bid

    # Withdrawal cost not amortized when available depth is too thin
    if min(bbo_buy.ask_qty, bbo_sell.bid_qty) < qty * settings.min_fill_ratio:
        return _build_rejected(opportunity, qty, _now, "SKIPPED_MIN_FILL")

    # Race condition: spread flipped between detection and execution
    if calculate_net_spread(buy_ex, sell_ex, buy_price, sell_price, qty) <= 0:
        return _build_rejected(opportunity, qty, _now, "ABORTED_STALE")

    fee_buy = calculate_fee(buy_ex, qty, buy_price, OrderSide.TAKER)
    fee_sell = calculate_fee(sell_ex, qty, sell_price, OrderSide.TAKER)
    cost_usdt = qty * buy_price + fee_buy

    wallet_buy = wallets.get(buy_ex)
    wallet_sell = wallets.get(sell_ex)
    if wallet_buy is None or wallet_sell is None:
        return _build_rejected(opportunity, qty, _now, "REJECTED_INSUFFICIENT_BALANCE")
    if wallet_buy.usdt < cost_usdt or wallet_sell.btc < qty:
        return _build_rejected(opportunity, qty, _now, "REJECTED_INSUFFICIENT_BALANCE")

    wallets[buy_ex] = wallet_buy.model_copy(update={
        "usdt": wallet_buy.usdt - cost_usdt,
        "btc": wallet_buy.btc + qty,
        "updated_at": _now,
    })
    wallets[sell_ex] = wallet_sell.model_copy(update={
        "usdt": wallet_sell.usdt + qty * sell_price - fee_sell,
        "btc": wallet_sell.btc - qty,
        "updated_at": _now,
    })

    net_profit = (sell_price - buy_price) * qty - fee_buy - fee_sell
    trade = Trade(
        id=str(uuid.uuid4()),
        buy_exchange=buy_ex,
        sell_exchange=sell_ex,
        qty=qty,
        buy_price=buy_price,
        sell_price=sell_price,
        fee_buy=fee_buy,
        fee_sell=fee_sell,
        slippage_est=0.0,
        net_profit=net_profit,
        status="EXECUTED",
        ws_received_at=opportunity.detected_at,
        decision_at=_now,
        latency_ms=(_now - opportunity.detected_at).total_seconds() * 1000,
        executed_at=_now,
    )
    _persist_trade(trade)
    return trade


def _build_rejected(
    opportunity: Opportunity,
    qty: float,
    now: datetime,
    status: TradeStatus,
) -> Trade:
    return Trade(
        id=str(uuid.uuid4()),
        buy_exchange=opportunity.buy_exchange,
        sell_exchange=opportunity.sell_exchange,
        qty=qty,
        buy_price=opportunity.buy_ask,
        sell_price=opportunity.sell_bid,
        fee_buy=0.0,
        fee_sell=0.0,
        slippage_est=0.0,
        net_profit=0.0,
        status=status,
        ws_received_at=opportunity.detected_at,
        decision_at=now,
        latency_ms=(now - opportunity.detected_at).total_seconds() * 1000,
        executed_at=now,
    )


def _persist_trade(trade: Trade) -> None:
    get_connection().execute(
        """
        INSERT INTO trades (
            id, opportunity_id, buy_exchange, sell_exchange,
            qty, buy_price, sell_price, fee_buy, fee_sell,
            slippage_est, net_profit, status,
            ws_received_at, decision_at, latency_ms, executed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            trade.id, None,
            trade.buy_exchange.value, trade.sell_exchange.value,
            trade.qty, trade.buy_price, trade.sell_price,
            trade.fee_buy, trade.fee_sell,
            trade.slippage_est, trade.net_profit, trade.status,
            trade.ws_received_at, trade.decision_at,
            trade.latency_ms, trade.executed_at,
        ],
    )
