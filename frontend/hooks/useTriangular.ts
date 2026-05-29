'use client'

import { useCallback, useEffect, useRef, useState } from 'react'

export interface TriangularLeg {
  src: string
  dst: string
  action: string           // "BUY" | "SELL" | "CONVERT"
  exchange: string | null  // null for CONVERT legs
  price: number | null
  fee_rate: number
  rate: number
}

export interface TriangularOpportunity {
  path: string             // e.g. "USDT→BTC→USD→USDT"
  cycle: string[]          // e.g. ["USDT","BTC","USD"]
  net_multiplier: number
  net_profit_pct: number   // e.g. 0.1385 means 0.1385%
  notional: number
  withdrawal_cost: number
  net_profit: number       // net_profit_pct * notional / 100 - withdrawal_cost
  legs: TriangularLeg[]
}

const BASE = 'http://localhost:8000'
const WS_URL = 'ws://localhost:8000/ws/live'
const POLL_MS = 2000
const RECONNECT_DELAY_MS = 3000

type WsMessage = { type: string; data: unknown }

async function fetchTriangular(): Promise<TriangularOpportunity[]> {
  try {
    const res = await fetch(`${BASE}/api/triangular`, { cache: 'no-store' })
    if (!res.ok) return []
    return (await res.json()) as TriangularOpportunity[]
  } catch {
    return []
  }
}

export function useTriangular(): TriangularOpportunity[] {
  const [opps, setOpps] = useState<TriangularOpportunity[]>([])
  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const deadRef = useRef(false)

  // Polling
  useEffect(() => {
    let cancelled = false

    async function poll() {
      const data = await fetchTriangular()
      if (!cancelled) {
        // Only replace with polled data if WS hasn't pushed anything recently.
        // We always accept polled data; WS updates will overwrite as they arrive.
        setOpps(data)
      }
    }

    void poll()
    const id = setInterval(() => { void poll() }, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  // WebSocket — filter for triangular_opportunity messages
  const connect = useCallback(() => {
    if (deadRef.current) return
    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onmessage = (event: MessageEvent<string>) => {
        if (deadRef.current) return
        try {
          const msg = JSON.parse(event.data) as WsMessage
          if (msg.type === 'triangular_opportunity') {
            const item = msg.data as TriangularOpportunity
            // Replace list entry keyed by path, keep most recent at top
            setOpps(prev => [
              item,
              ...prev.filter(o => o.path !== item.path),
            ].slice(0, 20))
          }
        } catch {
          // malformed message — skip silently
        }
      }

      ws.onclose = () => {
        if (deadRef.current) return
        timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
      }

      ws.onerror = () => {
        ws.close()
      }
    } catch {
      timerRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
    }
  }, [])

  useEffect(() => {
    deadRef.current = false
    connect()
    return () => {
      deadRef.current = true
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  return opps
}
