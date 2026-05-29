'use client'

import { type ZScoreData } from '@/hooks/useArbitrageData'
import { format, parseISO } from 'date-fns'

interface ZscorePanelProps {
  data: ZScoreData | null
}

function zscoreColor(z: number): string {
  const abs = Math.abs(z)
  if (abs >= 2) return 'text-red-400'
  if (abs >= 1) return 'text-yellow-400'
  return 'text-green-400'
}

function zscoreLabel(z: number): string {
  const abs = Math.abs(z)
  if (abs >= 2) return 'Extreme'
  if (abs >= 1) return 'Elevated'
  return 'Normal'
}

// Maps z in [-3, +3] to a 0-100 percentage for the gauge bar
function zToPercent(z: number): number {
  return Math.round(((Math.max(-3, Math.min(3, z)) + 3) / 6) * 100)
}

export function ZscorePanel({ data }: ZscorePanelProps) {
  return (
    <div className="rounded-lg border border-white/10 bg-gray-900 p-4 h-full">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
          Stat Arb Z-Score
        </h3>
        {data && (
          <span className="text-xs font-mono text-gray-500">
            {data.pair}
          </span>
        )}
      </div>

      {data === null ? (
        <div className="flex flex-col items-center justify-center h-32 gap-2">
          <div className="w-2 h-2 rounded-full bg-gray-600 animate-pulse" />
          <span className="text-xs text-gray-600">Waiting for stat arb data…</span>
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-end gap-2">
            <span className={`text-3xl font-bold font-mono ${zscoreColor(data.z_score)}`}>
              {data.z_score > 0 ? '+' : ''}{data.z_score.toFixed(2)}σ
            </span>
            <span className={`text-sm mb-1 ${zscoreColor(data.z_score)}`}>
              {zscoreLabel(data.z_score)}
            </span>
          </div>

          {/* Gauge bar: -3σ to +3σ */}
          <div className="relative h-3 rounded-full bg-white/5 overflow-hidden">
            {/* center line */}
            <div className="absolute left-1/2 top-0 w-px h-full bg-white/20" />
            {/* threshold markers at ±1σ and ±2σ */}
            <div className="absolute left-[33.3%] top-0 w-px h-full bg-yellow-500/30" />
            <div className="absolute left-[66.7%] top-0 w-px h-full bg-yellow-500/30" />
            {/* fill bar */}
            <div
              className={`absolute top-0 h-full transition-all duration-500 ${
                Math.abs(data.z_score) >= 2
                  ? 'bg-red-500/60'
                  : Math.abs(data.z_score) >= 1
                  ? 'bg-yellow-500/60'
                  : 'bg-green-500/60'
              }`}
              style={{
                left: `${Math.min(50, zToPercent(data.z_score))}%`,
                right: `${100 - Math.max(50, zToPercent(data.z_score))}%`,
              }}
            />
          </div>

          <div className="flex justify-between text-xs text-gray-600 font-mono">
            <span>-3σ</span>
            <span>-1σ</span>
            <span>0</span>
            <span>+1σ</span>
            <span>+3σ</span>
          </div>

          <div className="flex justify-between text-xs text-gray-500 pt-1 border-t border-white/5">
            <span>
              Spread: <span className="font-mono text-gray-300">${data.spread.toFixed(2)}</span>
            </span>
            <span className="font-mono text-gray-600">
              {format(parseISO(data.timestamp), 'HH:mm:ss')}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
