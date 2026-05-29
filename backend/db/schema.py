from __future__ import annotations

from db.connection import get_connection

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS opportunities (
    id            VARCHAR PRIMARY KEY,
    buy_exchange  VARCHAR NOT NULL,
    sell_exchange VARCHAR NOT NULL,
    buy_ask       DOUBLE NOT NULL,
    sell_bid      DOUBLE NOT NULL,
    gross_spread  DOUBLE NOT NULL,
    net_spread    DOUBLE NOT NULL,
    score         DOUBLE NOT NULL,
    optimal_qty   DOUBLE NOT NULL,
    status        VARCHAR NOT NULL,
    detected_at   TIMESTAMPTZ NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS trades (
    id             VARCHAR PRIMARY KEY,
    opportunity_id VARCHAR,
    buy_exchange   VARCHAR NOT NULL,
    sell_exchange  VARCHAR NOT NULL,
    qty            DOUBLE NOT NULL,
    buy_price      DOUBLE NOT NULL,
    sell_price     DOUBLE NOT NULL,
    fee_buy        DOUBLE NOT NULL,
    fee_sell       DOUBLE NOT NULL,
    slippage_est   DOUBLE NOT NULL,
    net_profit     DOUBLE NOT NULL,
    status         VARCHAR NOT NULL,
    ws_received_at TIMESTAMPTZ NOT NULL,
    decision_at    TIMESTAMPTZ NOT NULL,
    latency_ms     DOUBLE NOT NULL,
    executed_at    TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS balances (
    exchange   VARCHAR NOT NULL,
    asset      VARCHAR NOT NULL,
    amount     DOUBLE NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (exchange, asset)
);

CREATE SEQUENCE IF NOT EXISTS latency_seq START 1;

CREATE TABLE IF NOT EXISTS latency_events (
    id             BIGINT DEFAULT nextval('latency_seq'),
    ws_received_at TIMESTAMPTZ NOT NULL,
    normalized_at  TIMESTAMPTZ,
    scanned_at     TIMESTAMPTZ,
    decision_at    TIMESTAMPTZ NOT NULL,
    latency_ms     DOUBLE NOT NULL,
    created_at     TIMESTAMPTZ DEFAULT now()
);
"""


def initialize_schema() -> None:
    conn = get_connection()
    conn.execute(_SCHEMA_SQL)
