'use client'

import { useEffect, useState } from 'react'

export type LiquidityStatus = 'HEALTHY' | 'DEGRADED' | 'UNKNOWN'

export interface ExchangeHealth {
  key: string
  connected: boolean
  liquidityStatus: LiquidityStatus | null
  liquidityScore: number | null
  levelCount: number | null
}

export interface SystemHealth {
  exchanges: ExchangeHealth[]
  uptimeS: number
  depthWithData: number
  loading: boolean
}

const KNOWN_EXCHANGES = ['binance', 'kraken', 'coinbase', 'okx']
const BASE = 'http://localhost:8000'
const POLL_MS = 5_000

interface LiquidityEntry {
  score: number
  status: string
  level_count: number
  computed_at: string
}

interface StatusResponse {
  exchanges_connected: string[]
  liquidity_health: Record<string, LiquidityEntry>
  uptime_s: number
}

export function useSystemHealth(): SystemHealth {
  const [health, setHealth] = useState<SystemHealth>({
    exchanges: KNOWN_EXCHANGES.map(key => ({
      key,
      connected: false,
      liquidityStatus: null,
      liquidityScore: null,
      levelCount: null,
    })),
    uptimeS: 0,
    depthWithData: 0,
    loading: true,
  })

  useEffect(() => {
    let cancelled = false

    async function poll() {
      try {
        const res = await fetch(`${BASE}/api/status`, { cache: 'no-store' })
        if (!res.ok || cancelled) return
        const data = (await res.json()) as StatusResponse

        const connectedSet = new Set(
          (data.exchanges_connected ?? []).map((s: string) => s.toLowerCase()),
        )
        const liqHealth: Record<string, LiquidityEntry> = data.liquidity_health ?? {}

        const exchanges: ExchangeHealth[] = KNOWN_EXCHANGES.map(key => {
          const liq = liqHealth[key] ?? null
          return {
            key,
            connected: connectedSet.has(key),
            liquidityStatus: liq ? (liq.status as LiquidityStatus) : null,
            liquidityScore: liq ? liq.score : null,
            levelCount: liq ? liq.level_count : null,
          }
        })

        const depthWithData = exchanges.filter(e => e.liquidityStatus !== null).length

        if (!cancelled) {
          setHealth({
            exchanges,
            uptimeS: data.uptime_s ?? 0,
            depthWithData,
            loading: false,
          })
        }
      } catch {
        if (!cancelled) setHealth(prev => ({ ...prev, loading: false }))
      }
    }

    void poll()
    const id = setInterval(() => { void poll() }, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  return health
}
