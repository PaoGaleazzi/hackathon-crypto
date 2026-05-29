'use client'

import { useEffect, useState } from 'react'

export interface RebalanceTransfer {
  asset: string
  from: string
  to: string
  amount: number
  fee_usd: number
}

export interface RebalancePlan {
  status: string             // "OK" | "BALANCED" | "INFEASIBLE" | "NONE"
  total_cost_usd: number
  n_transfers: number
  transfers: RebalanceTransfer[]
  computed_at: string | null
}

const BASE = 'http://localhost:8000'
const WS_URL = 'ws://localhost:8000/ws/live'
const POLL_MS = 2000
const RECONNECT_DELAY_MS = 3000

type WsMessage = { type: string; data: unknown }

async function fetchRebalance(): Promise<RebalancePlan | null> {
  try {
    const res = await fetch(`${BASE}/api/rebalance`, { cache: 'no-store' })
    if (!res.ok) return null
    return (await res.json()) as RebalancePlan
  } catch {
    return null
  }
}

export function useRebalance(): RebalancePlan | null {
  const [plan, setPlan] = useState<RebalancePlan | null>(null)

  // Polling — endpoint includes computed_at, unlike the WS push.
  useEffect(() => {
    let cancelled = false

    async function poll() {
      const data = await fetchRebalance()
      if (!cancelled && data) setPlan(data)
    }

    void poll()
    const id = setInterval(() => { void poll() }, POLL_MS)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

  // WebSocket — filter for rebalance messages. The push carries computed_at
  // (exact server timestamp); fall back to client time only if it's absent.
  useEffect(() => {
    let dead = false
    let ws: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | null = null

    function connect() {
      if (dead) return
      try {
        ws = new WebSocket(WS_URL)

        ws.onmessage = (event: MessageEvent<string>) => {
          if (dead) return
          try {
            const msg = JSON.parse(event.data) as WsMessage
            if (msg.type === 'rebalance') {
              const data = msg.data as RebalancePlan
              setPlan({
                ...data,
                computed_at: data.computed_at ?? new Date().toISOString(),
              })
            }
          } catch {
            // malformed message — skip silently
          }
        }

        ws.onclose = () => {
          if (dead) return
          timer = setTimeout(connect, RECONNECT_DELAY_MS)
        }

        ws.onerror = () => {
          ws?.close()
        }
      } catch {
        timer = setTimeout(connect, RECONNECT_DELAY_MS)
      }
    }

    connect()
    return () => {
      dead = true
      if (timer) clearTimeout(timer)
      ws?.close()
    }
  }, [])

  return plan
}
