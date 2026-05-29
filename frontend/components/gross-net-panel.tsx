'use client'

import type { Opportunity } from '@/lib/mock-data'

interface Props {
  opportunities: Opportunity[]
}

export function GrossNetPanel({ opportunities }: Props) {
  const gross = opportunities
  const net = opportunities.filter(o => o.net_spread > 0)
  const rejected = opportunities.filter(o => o.net_spread <= 0)

  const grossProfit = gross.reduce((sum, o) => sum + o.gross_spread * o.optimal_qty, 0)
  const netProfit = net.reduce((sum, o) => sum + o.net_spread * o.optimal_qty, 0)
  const rejectedPct = gross.length > 0 ? (rejected.length / gross.length) * 100 : 0
  const netSurvivePct = gross.length > 0 ? (net.length / gross.length) * 100 : 0

  return (
    <div
      className="rounded-xl border p-5"
      style={{ background: '#111827', borderColor: '#1f2937' }}
    >
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
          Gross vs Net Filter
        </h3>
        <span className="text-xs px-2 py-0.5 rounded-full font-mono"
          style={{ background: '#1e2d1e', color: '#4ade80' }}>
          Criterio 2 — Fee Awareness
        </span>
      </div>

      {/* Main two-column comparison */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        {/* GROSS column */}
        <div
          className="rounded-lg p-4 border"
          style={{ background: '#1a1505', borderColor: '#78350f' }}
        >
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full" style={{ background: '#f59e0b' }} />
            <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#f59e0b' }}>
              Gross (antes de fees)
            </span>
          </div>
          <p className="text-3xl font-bold font-mono text-white mb-1">{gross.length}</p>
          <p className="text-xs text-gray-500 mb-3">oportunidades detectadas</p>
          <div className="pt-3 border-t" style={{ borderColor: '#78350f' }}>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Profit teórico</p>
            <p className="text-lg font-mono font-semibold" style={{ color: '#fbbf24' }}>
              +${grossProfit.toFixed(2)}
            </p>
          </div>
        </div>

        {/* NET column */}
        <div
          className="rounded-lg p-4 border"
          style={{ background: '#0d1a12', borderColor: '#14532d' }}
        >
          <div className="flex items-center gap-2 mb-3">
            <div className="w-2 h-2 rounded-full" style={{ background: '#22c55e' }} />
            <span className="text-xs font-semibold uppercase tracking-widest" style={{ color: '#22c55e' }}>
              Net (ejecutables)
            </span>
          </div>
          <p className="text-3xl font-bold font-mono text-white mb-1">{net.length}</p>
          <p className="text-xs text-gray-500 mb-3">superan fees + slippage</p>
          <div className="pt-3 border-t" style={{ borderColor: '#14532d' }}>
            <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">Profit neto real</p>
            <p className="text-lg font-mono font-semibold" style={{ color: '#4ade80' }}>
              +${netProfit.toFixed(2)}
            </p>
          </div>
        </div>
      </div>

      {/* Funnel bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-gray-500">Distribución del pipeline</span>
          <span className="text-xs font-mono text-gray-400">{gross.length} total</span>
        </div>
        <div className="flex h-3 rounded-full overflow-hidden gap-0.5" style={{ background: '#1f2937' }}>
          {gross.length > 0 && (
            <>
              <div
                className="h-full rounded-l-full transition-all"
                style={{ width: `${netSurvivePct}%`, background: '#22c55e' }}
                title={`Ejecutables: ${net.length}`}
              />
              <div
                className="h-full rounded-r-full transition-all"
                style={{ width: `${rejectedPct}%`, background: '#ef4444' }}
                title={`Rechazadas: ${rejected.length}`}
              />
            </>
          )}
        </div>
        <div className="flex justify-between mt-1.5">
          <span className="text-xs font-mono" style={{ color: '#22c55e' }}>
            {netSurvivePct.toFixed(0)}% ejecutables
          </span>
          <span className="text-xs font-mono" style={{ color: '#ef4444' }}>
            {rejectedPct.toFixed(0)}% rechazadas
          </span>
        </div>
      </div>

      {/* Rejection highlight */}
      <div
        className="rounded-lg p-3 border flex items-center justify-between"
        style={{ background: '#1a0d0d', borderColor: '#7f1d1d' }}
      >
        <div className="flex items-center gap-2.5">
          <svg className="w-4 h-4 shrink-0" style={{ color: '#f87171' }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
          </svg>
          <div>
            <p className="text-xs text-gray-400">
              <span className="font-semibold text-white">{rejected.length} oportunidades</span>
              {' '}rechazadas correctamente — positivas en bruto, <span className="font-semibold" style={{ color: '#f87171' }}>negativas en neto</span>
            </p>
          </div>
        </div>
        <span
          className="text-xl font-bold font-mono ml-4 shrink-0"
          style={{ color: '#f87171' }}
        >
          {rejectedPct.toFixed(0)}%
        </span>
      </div>
    </div>
  )
}
