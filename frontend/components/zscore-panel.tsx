'use client'

import { type ZScoreData, type ZScorePoint } from '@/hooks/useArbitrageData'
import { format, parseISO } from 'date-fns'

interface ZscorePanelProps {
  data: ZScoreData | null
  history?: ZScorePoint[]
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

const SVG_W = 220
const SVG_H = 44

function ZScoreSparkline({ history }: { history: ZScorePoint[] }) {
  if (history.length < 2) {
    return (
      <div className="flex items-center justify-center h-11 text-xs text-gray-600">
        Accumulating history…
      </div>
    )
  }

  const zValues = history.map(p => p.z)
  const minZ = Math.min(-3, ...zValues)
  const maxZ = Math.max(3, ...zValues)
  const range = maxZ - minZ || 1

  const toX = (i: number) => (i / (history.length - 1)) * SVG_W
  const toY = (z: number) => SVG_H - ((z - minZ) / range) * SVG_H

  const points = history.map((p, i) => `${toX(i).toFixed(1)},${toY(p.z).toFixed(1)}`).join(' ')

  const zeroY = toY(0)
  const pos2Y = toY(2)
  const neg2Y = toY(-2)

  // Gradient fill: split above/below zero
  const lastZ = history[history.length - 1].z
  const strokeColor = Math.abs(lastZ) >= 2 ? '#f87171' : Math.abs(lastZ) >= 1 ? '#facc15' : '#4ade80'

  return (
    <svg
      width="100%"
      height={SVG_H}
      viewBox={`0 0 ${SVG_W} ${SVG_H}`}
      preserveAspectRatio="none"
      className="overflow-visible"
    >
      {/* ±2σ threshold bands */}
      {pos2Y >= 0 && pos2Y <= SVG_H && (
        <line x1="0" y1={pos2Y} x2={SVG_W} y2={pos2Y}
          stroke="rgba(239,68,68,0.25)" strokeWidth="1" strokeDasharray="3,3" />
      )}
      {neg2Y >= 0 && neg2Y <= SVG_H && (
        <line x1="0" y1={neg2Y} x2={SVG_W} y2={neg2Y}
          stroke="rgba(239,68,68,0.25)" strokeWidth="1" strokeDasharray="3,3" />
      )}
      {/* Zero line */}
      {zeroY >= 0 && zeroY <= SVG_H && (
        <line x1="0" y1={zeroY} x2={SVG_W} y2={zeroY}
          stroke="rgba(255,255,255,0.12)" strokeWidth="1" />
      )}
      {/* Z-score sparkline */}
      <polyline
        points={points}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      {/* Current value dot */}
      {history.length >= 1 && (
        <circle
          cx={toX(history.length - 1).toFixed(1)}
          cy={toY(lastZ).toFixed(1)}
          r="2.5"
          fill={strokeColor}
        />
      )}
    </svg>
  )
}

export function ZscorePanel({ data, history = [] }: ZscorePanelProps) {
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

          {/* Historical sparkline */}
          <div className="border-t border-white/5 pt-2">
            <div className="flex justify-between text-xs text-gray-600 mb-1">
              <span>History ({history.length} pts)</span>
              <span className="font-mono">±2σ threshold</span>
            </div>
            <ZScoreSparkline history={history} />
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
