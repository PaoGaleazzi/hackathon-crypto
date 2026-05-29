import {
  TrendingUp,
  Search,
  BarChart2,
  Zap,
} from 'lucide-react'
import { type Metrics } from '@/lib/mock-data'

interface MetricCardsProps {
  metrics: Metrics
}

function formatCurrency(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function latencyColor(ms: number): string {
  if (ms < 50) return '#4ade80'
  if (ms < 150) return '#fbbf24'
  return '#f87171'
}

export function MetricCards({ metrics }: MetricCardsProps) {
  const pnlPositive = metrics.total_pnl_usdt >= 0

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
      {/* Total P&L */}
      <div
        className="relative overflow-hidden rounded-xl border p-5"
        style={{
          background: 'linear-gradient(135deg, #0f1629 0%, #1a1040 100%)',
          borderColor: '#1f2937',
        }}
      >
        <div className="flex items-start justify-between mb-3">
          <p className="text-[10px] uppercase tracking-widest text-gray-500">Total P&amp;L</p>
          <div
            className="flex items-center justify-center w-10 h-10 rounded-lg flex-shrink-0"
            style={{ background: 'rgba(74,222,128,0.10)' }}
          >
            <TrendingUp className="w-5 h-5 text-green-400" />
          </div>
        </div>
        <p
          className="text-3xl font-bold"
          style={{ color: pnlPositive ? '#4ade80' : '#f87171' }}
        >
          {formatCurrency(metrics.total_pnl_usdt)}
        </p>
        <p className="text-[11px] text-gray-600 mt-1">Cumulative net profit</p>
        <div
          className="absolute bottom-0 left-0 right-0 h-0.5 rounded-b-xl"
          style={{ background: 'linear-gradient(to right, #6366f1, #8b5cf6)' }}
        />
      </div>

      {/* Opportunities */}
      <div
        className="relative overflow-hidden rounded-xl border p-5"
        style={{
          background: 'linear-gradient(135deg, #0f1629 0%, #1a1040 100%)',
          borderColor: '#1f2937',
        }}
      >
        <div className="flex items-start justify-between mb-3">
          <p className="text-[10px] uppercase tracking-widest text-gray-500">Opportunities</p>
          <div
            className="flex items-center justify-center w-10 h-10 rounded-lg flex-shrink-0"
            style={{ background: 'rgba(99,102,241,0.10)' }}
          >
            <Search className="w-5 h-5 text-indigo-400" />
          </div>
        </div>
        <p className="text-3xl font-bold text-white">
          {metrics.opportunities_today.toLocaleString('en-US')}
        </p>
        <p className="text-[11px] text-gray-600 mt-1">Detected total</p>
        <div
          className="absolute bottom-0 left-0 right-0 h-0.5 rounded-b-xl"
          style={{ background: 'linear-gradient(to right, #6366f1, #8b5cf6)' }}
        />
      </div>

      {/* Best Spread */}
      <div
        className="relative overflow-hidden rounded-xl border p-5"
        style={{
          background: 'linear-gradient(135deg, #0f1629 0%, #1a1040 100%)',
          borderColor: '#1f2937',
        }}
      >
        <div className="flex items-start justify-between mb-3">
          <p className="text-[10px] uppercase tracking-widest text-gray-500">Best Spread</p>
          <div
            className="flex items-center justify-center w-10 h-10 rounded-lg flex-shrink-0"
            style={{ background: 'rgba(251,191,36,0.10)' }}
          >
            <BarChart2 className="w-5 h-5 text-amber-400" />
          </div>
        </div>
        <p className="text-3xl font-bold text-white">
          {metrics.best_spread_pct.toFixed(2)}
          <span className="text-xl font-medium text-gray-400 ml-0.5">%</span>
        </p>
        <p className="text-[11px] text-gray-600 mt-1">Maximum spread</p>
        <div
          className="absolute bottom-0 left-0 right-0 h-0.5 rounded-b-xl"
          style={{ background: 'linear-gradient(to right, #6366f1, #8b5cf6)' }}
        />
      </div>

      {/* Latency p95 */}
      <div
        className="relative overflow-hidden rounded-xl border p-5"
        style={{
          background: 'linear-gradient(135deg, #0f1629 0%, #1a1040 100%)',
          borderColor: '#1f2937',
        }}
      >
        <div className="flex items-start justify-between mb-3">
          <p className="text-[10px] uppercase tracking-widest text-gray-500">Latency p95</p>
          <div
            className="flex items-center justify-center w-10 h-10 rounded-lg flex-shrink-0"
            style={{ background: `${latencyColor(metrics.p95_latency_ms)}1a` }}
          >
            <Zap
              className="w-5 h-5"
              style={{ color: latencyColor(metrics.p95_latency_ms) }}
            />
          </div>
        </div>
        <p
          className="text-3xl font-bold"
          style={{ color: latencyColor(metrics.p95_latency_ms) }}
        >
          {metrics.p95_latency_ms.toLocaleString('en-US')}
          <span className="text-xl font-medium text-gray-400 ml-0.5">ms</span>
        </p>
        <p className="text-[11px] text-gray-600 mt-1">95th percentile</p>
        <div
          className="absolute bottom-0 left-0 right-0 h-0.5 rounded-b-xl"
          style={{ background: 'linear-gradient(to right, #6366f1, #8b5cf6)' }}
        />
      </div>
    </div>
  )
}
