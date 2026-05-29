'use client'

import { useEffect, useState } from 'react'
import type { Exchange, Metrics, Opportunity, Trade } from '@/lib/mock-data'

export interface LatencyStages {
  parse_p50_ms:    number | null
  parse_p95_ms:    number | null
  scan_p50_ms:     number | null
  scan_p95_ms:     number | null
  decision_p50_ms: number | null
  decision_p95_ms: number | null
}

interface PolledData {
  metrics: Metrics | null
  opportunities: Opportunity[]
  trades: Trade[]
  backendAlive: boolean
  latencyStages: LatencyStages | null
  latencySampleCount: number
  latencyP50Ms: number
  latencyP95Ms: number
}

interface StatusResponse {
  circuit_breaker: 'OPEN' | 'CLOSED'
  exchanges_connected: string[]
  uptime_s: number
}

interface LatencyResponse {
  p50_ms: number | null
  p95_ms: number | null
  p99_ms: number | null
  sample_count: number
  stages?: LatencyStages | null
}

interface PnlResponse {
  cumulative_pnl_usd: number
  trade_count: number
}

const BASE = 'http://localhost:8000'
const POLL_MS = 2000

async function fetchJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${path}`, { cache: 'no-store' })
    if (!res.ok) return null
    return (await res.json()) as T
  } catch {
    return null
  }
}

// Backend returns lowercase ("binance", "okx"); components expect PascalCase ("Binance").
function capitalizeExchange(raw: string): Exchange {
  return (raw.charAt(0).toUpperCase() + raw.slice(1)) as Exchange
}

export function useMetrics(): PolledData {
  const [data, setData] = useState<PolledData>({
    metrics: null,
    opportunities: [],
    trades: [],
    backendAlive: false,
    latencyStages: null,
    latencySampleCount: 0,
    latencyP50Ms: 0,
    latencyP95Ms: 0,
  })

  useEffect(() => {
    let cancelled = false

    async function poll() {
      const [opps, trades, status, latency, pnl] = await Promise.all([
        fetchJson<Opportunity[]>('/api/opportunities'),
        fetchJson<Trade[]>('/api/trades'),
        fetchJson<StatusResponse>('/api/status'),
        fetchJson<LatencyResponse>('/api/metrics/latency'),
        fetchJson<PnlResponse>('/api/pnl'),
      ])

      if (cancelled) return

      if (status === null) {
        setData(prev => ({ ...prev, backendAlive: false }))
        return
      }

      const resolvedOpps = opps ?? []
      const resolvedTrades = trades ?? []

      const bestSpread =
        resolvedOpps.length > 0
          ? Math.max(...resolvedOpps.map(o =>
              o.buy_ask > 0 ? (o.sell_bid - o.buy_ask) / o.buy_ask * 100 : 0
            ))
          : 0

      const metrics: Metrics = {
        total_pnl_usdt: pnl?.cumulative_pnl_usd ?? 0,
        opportunities_today: resolvedOpps.length,
        best_spread_pct: bestSpread,
        p95_latency_ms: latency?.p95_ms ?? 0,
        circuit_breaker: status.circuit_breaker,
        bot_active: true,
        exchanges_connected: status.exchanges_connected.map(capitalizeExchange),
      }

      setData({
        metrics,
        opportunities: resolvedOpps,
        trades: resolvedTrades,
        backendAlive: true,
        latencyStages: latency?.stages ?? null,
        latencySampleCount: latency?.sample_count ?? 0,
        latencyP50Ms: latency?.p50_ms ?? 0,
        latencyP95Ms: latency?.p95_ms ?? 0,
      })
    }

    void poll()
    const id = setInterval(() => { void poll() }, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return data
}
