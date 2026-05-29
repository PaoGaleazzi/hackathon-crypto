from __future__ import annotations

import asyncio

from fastapi import APIRouter

import data.bbo_state as bbo_state
from core.circuit_breaker import get_circuit_breaker
from core.liquidity_health import get_liquidity_monitor
from db.connection import get_connection

router = APIRouter(tags=["metrics"])


@router.get("/metrics/summary")
async def get_summary_metrics() -> dict:
    def _query() -> dict:
        conn = get_connection()

        pnl_row = conn.execute("""
            SELECT
                COALESCE(SUM(net_profit), 0.0) AS total_pnl,
                COUNT(*) FILTER (WHERE executed_at::date = current_date) AS count_today,
                COALESCE(MAX(net_profit), 0.0) AS best_spread_usd
            FROM trades
            WHERE status = 'EXECUTED'
        """).fetchone()

        return {
            "total_pnl_usd": pnl_row[0],
            "trade_count_today": pnl_row[1],
            "best_spread_usd": pnl_row[2],
        }

    return await asyncio.to_thread(_query)


@router.get("/metrics/latency")
async def get_latency_metrics() -> dict:
    def _query() -> dict:
        conn = get_connection()

        count_row = conn.execute("SELECT COUNT(*) FROM latency_events").fetchone()
        if count_row is None or count_row[0] == 0:
            return {
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "sample_count": 0,
                "stages": None,
            }

        row = conn.execute("""
            SELECT
                quantile_cont(latency_ms, 0.50) AS p50,
                quantile_cont(latency_ms, 0.95) AS p95,
                quantile_cont(latency_ms, 0.99) AS p99,
                COUNT(*)                         AS sample_count,

                -- parse: WS received → BBO normalized
                quantile_cont(
                    (epoch_ms(normalized_at) - epoch_ms(ws_received_at))::DOUBLE,
                    0.50
                ) FILTER (WHERE normalized_at IS NOT NULL)              AS parse_p50,

                quantile_cont(
                    (epoch_ms(normalized_at) - epoch_ms(ws_received_at))::DOUBLE,
                    0.95
                ) FILTER (WHERE normalized_at IS NOT NULL)              AS parse_p95,

                -- scan: BBO normalized → scanner started
                quantile_cont(
                    (epoch_ms(scanned_at) - epoch_ms(normalized_at))::DOUBLE,
                    0.50
                ) FILTER (WHERE normalized_at IS NOT NULL
                            AND scanned_at  IS NOT NULL)                AS scan_p50,

                quantile_cont(
                    (epoch_ms(scanned_at) - epoch_ms(normalized_at))::DOUBLE,
                    0.95
                ) FILTER (WHERE normalized_at IS NOT NULL
                            AND scanned_at  IS NOT NULL)                AS scan_p95,

                -- decision: scanner started → trade decision
                quantile_cont(
                    (epoch_ms(decision_at) - epoch_ms(scanned_at))::DOUBLE,
                    0.50
                ) FILTER (WHERE scanned_at IS NOT NULL)                 AS decision_p50,

                quantile_cont(
                    (epoch_ms(decision_at) - epoch_ms(scanned_at))::DOUBLE,
                    0.95
                ) FILTER (WHERE scanned_at IS NOT NULL)                 AS decision_p95

            FROM latency_events
        """).fetchone()

        if row is None or row[0] is None:
            return {
                "p50_ms": 0,
                "p95_ms": 0,
                "p99_ms": 0,
                "sample_count": 0,
                "stages": None,
            }

        stages = None
        if row[4] is not None:
            stages = {
                "parse_p50_ms":    round(row[4], 3),
                "parse_p95_ms":    round(row[5], 3) if row[5] is not None else None,
                "scan_p50_ms":     round(row[6], 3) if row[6] is not None else None,
                "scan_p95_ms":     round(row[7], 3) if row[7] is not None else None,
                "decision_p50_ms": round(row[8], 3) if row[8] is not None else None,
                "decision_p95_ms": round(row[9], 3) if row[9] is not None else None,
            }

        return {
            "p50_ms":       round(row[0], 3),
            "p95_ms":       round(row[1], 3),
            "p99_ms":       round(row[2], 3),
            "sample_count": row[3],
            "stages":       stages,
        }

    return await asyncio.to_thread(_query)


@router.get("/status")
async def get_status() -> dict:
    cb = get_circuit_breaker()
    return {
        "circuit_breaker": cb.state.value,
        "circuit_breaker_detail": cb.as_dict(),
        "exchanges_connected": bbo_state.get_connected(),
        "liquidity_health": get_liquidity_monitor().as_dict(),
        "uptime_s": 0,
    }
