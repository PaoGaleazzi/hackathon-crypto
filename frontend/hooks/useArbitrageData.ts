'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import type { Opportunity, PnlPoint, Trade, SpreadCandle } from '@/lib/mock-data'

export interface ZScoreData {
  pair: string
  z_score: number
  spread: number
  timestamp: string
}

export interface ZScorePoint {
  time: number
  z: number
}

interface ArbitrageState {
  opportunities: Opportunity[]
  trades: Trade[]
  pnlPoints: PnlPoint[]
  connected: boolean
  latestLatencyMs: number | null
  zScore: ZScoreData | null
  circuitBreaker: 'OPEN' | 'CLOSED' | null
  btcPrices: Record<string, number>
  zScoreHistory: ZScorePoint[]
  priceHistory: Record<string, number[]>
  spreadCandles: SpreadCandle[]
}

type WsMessage =
  | { type: 'opportunity'; data: Opportunity }
  | { type: 'trade'; data: Trade }
  | { type: 'pnl_update'; data: PnlPoint }
  | { type: 'z_score'; data: ZScoreData }
  | { type: 'circuit_breaker'; data: { state: 'OPEN' | 'CLOSED' } }

const WS_URL = 'ws://localhost:8000/ws/live'
const RECONNECT_DELAY_MS = 3000
const MAX_ROWS = 20
const MAX_PNL_POINTS = 200
const MAX_ZSCORE_HISTORY = 120

export function useArbitrageData(): ArbitrageState {
  const [state, setState] = useState<ArbitrageState>({
    opportunities: [],
    trades: [],
    pnlPoints: [],
    connected: false,
    latestLatencyMs: null,
    zScore: null,
    circuitBreaker: null,
    btcPrices: {},
    zScoreHistory: [],
    priceHistory: {},
    spreadCandles: [],
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
              case 'opportunity': {
                const prices = { ...prev.btcPrices }
                prices[msg.data.buy_exchange] = msg.data.buy_ask
                prices[msg.data.sell_exchange] = msg.data.sell_bid

                // Update last-20 price history per exchange
                const hist = { ...prev.priceHistory }
                const buyEx = msg.data.buy_exchange
                const sellEx = msg.data.sell_exchange
                hist[buyEx] = [...(hist[buyEx] ?? []), msg.data.buy_ask].slice(-20)
                hist[sellEx] = [...(hist[sellEx] ?? []), msg.data.sell_bid].slice(-20)

                // Build live spread candles for binance↔kraken pair (any order)
                const exchanges = new Set([buyEx, sellEx])
                let nextCandles = prev.spreadCandles
                if (exchanges.has('binance') && exchanges.has('kraken')) {
                  const spread = Math.abs(msg.data.sell_bid - msg.data.buy_ask)
                  const fiveSecKey = Math.floor(Date.now() / 5000) * 5
                  const last = nextCandles[nextCandles.length - 1]
                  if (last && last.time === fiveSecKey) {
                    const updated: SpreadCandle = {
                      ...last,
                      high: Math.max(last.high, spread),
                      low: Math.min(last.low, spread),
                      close: spread,
                    }
                    nextCandles = [...nextCandles.slice(0, -1), updated]
                  } else {
                    nextCandles = [
                      ...nextCandles,
                      { time: fiveSecKey, open: spread, high: spread, low: spread, close: spread },
                    ].slice(-200)
                  }
                }

                return {
                  ...prev,
                  opportunities: [msg.data, ...prev.opportunities].slice(0, MAX_ROWS),
                  btcPrices: prices,
                  priceHistory: hist,
                  spreadCandles: nextCandles,
                }
              }
              case 'trade':
                return {
                  ...prev,
                  trades: [msg.data, ...prev.trades].slice(0, MAX_ROWS),
                  latestLatencyMs: msg.data.latency_ms,
                }
              case 'pnl_update':
                return {
                  ...prev,
                  pnlPoints: [...prev.pnlPoints, msg.data].slice(-MAX_PNL_POINTS),
                }
              case 'z_score':
                return {
                  ...prev,
                  zScore: msg.data,
                  zScoreHistory: [
                    ...prev.zScoreHistory,
                    { time: Date.now(), z: msg.data.z_score },
                  ].slice(-MAX_ZSCORE_HISTORY),
                }
              case 'circuit_breaker':
                return { ...prev, circuitBreaker: msg.data.state }
              default:
                return prev
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
