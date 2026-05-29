'use client'

import { useState } from 'react'
import { Badge } from '@/components/ui/badge'
import { ShieldAlert, ShieldCheck, RotateCcw, Zap } from 'lucide-react'

interface CircuitBreakerPanelProps {
  state: 'OPEN' | 'CLOSED'
  onStateChange?: (newState: 'OPEN' | 'CLOSED') => void
}

const BASE = 'http://localhost:8000'

export function CircuitBreakerPanel({ state, onStateChange }: CircuitBreakerPanelProps) {
  const [loading, setLoading] = useState<'reset' | 'open' | null>(null)
  const [lastAction, setLastAction] = useState<string | null>(null)

  async function callCb(action: 'reset' | 'open') {
    setLoading(action)
    try {
      const endpoint = action === 'reset' ? '/api/circuit-breaker/reset' : '/api/circuit-breaker/open'
      const res = await fetch(`${BASE}${endpoint}`, { method: 'POST' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = (await res.json()) as { state: 'OPEN' | 'CLOSED' }
      onStateChange?.(data.state)
      setLastAction(action === 'reset' ? 'Closed — counters reset' : 'Forced open')
    } catch (err) {
      setLastAction(`Error: ${err instanceof Error ? err.message : 'request failed'}`)
    } finally {
      setLoading(null)
    }
  }

  const isOpen = state === 'OPEN'

  return (
    <div className="rounded-lg border border-white/10 bg-gray-900 p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
          Circuit Breaker
        </h3>
        <Badge
          variant="outline"
          className={isOpen
            ? 'border-red-500/50 text-red-400'
            : 'border-green-500/50 text-green-400'}
        >
          {isOpen
            ? <ShieldAlert className="w-3 h-3 mr-1 inline" />
            : <ShieldCheck className="w-3 h-3 mr-1 inline" />}
          {state}
        </Badge>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => void callCb('reset')}
          disabled={loading !== null}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
            bg-green-500/10 text-green-400 border border-green-500/30
            hover:bg-green-500/20 disabled:opacity-40 disabled:cursor-not-allowed
            transition-colors"
        >
          <RotateCcw className={`w-3 h-3 ${loading === 'reset' ? 'animate-spin' : ''}`} />
          Reset (Close)
        </button>

        <button
          onClick={() => void callCb('open')}
          disabled={loading !== null}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium
            bg-red-500/10 text-red-400 border border-red-500/30
            hover:bg-red-500/20 disabled:opacity-40 disabled:cursor-not-allowed
            transition-colors"
        >
          <Zap className={`w-3 h-3 ${loading === 'open' ? 'animate-pulse' : ''}`} />
          Force Open
        </button>

        {lastAction && (
          <span className="text-xs text-gray-500 ml-1">{lastAction}</span>
        )}
      </div>
    </div>
  )
}
