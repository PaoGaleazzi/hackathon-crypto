'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { Opportunity, PnlPoint, Trade } from '@/lib/mock-data'

interface ArbitrageState {
  opportunities: Opportunity[]
  trades: Trade[]
  pnlPoints: PnlPoint[]
  connected: boolean
}

type WsMessage =
  | { type: 'opportunity'; data: Opportunity }
  | { type: 'trade'; data: Trade }
  | { type: 'pnl_update'; data: PnlPoint }

const WS_URL = 'ws://localhost:8000/ws/live'
const RECONNECT_DELAY_MS = 3000
const MAX_ROWS = 20
const MAX_PNL_POINTS = 200

export function useArbitrageData(): ArbitrageState {
  const [state, setState] = useState<ArbitrageState>({
    opportunities: [],
    trades: [],
    pnlPoints: [],
    connected: false,
  })
  const wsRef = useRef<WebSocket | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const deadRef = useRef(false)

  const connect = useCallback(() => {
    if (deadRef.current) return
    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (deadRef.current) return
        setState(prev => ({ ...prev, connected: true }))
      }

      ws.onmessage = (event: MessageEvent<string>) => {
        if (deadRef.current) return
        try {
          const msg = JSON.parse(event.data) as WsMessage
          setState(prev => {
            switch (msg.type) {
              case 'opportunity':
                return {
                  ...prev,
                  opportunities: [msg.data, ...prev.opportunities].slice(0, MAX_ROWS),
                }
              case 'trade':
                return {
                  ...prev,
                  trades: [msg.data, ...prev.trades].slice(0, MAX_ROWS),
                }
              case 'pnl_update':
                return {
                  ...prev,
                  pnlPoints: [...prev.pnlPoints, msg.data].slice(-MAX_PNL_POINTS),
                }
            }
          })
        } catch {
          // malformed message — skip silently
        }
      }

      ws.onclose = () => {
        if (deadRef.current) return
        setState(prev => ({ ...prev, connected: false }))
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

  return state
}
