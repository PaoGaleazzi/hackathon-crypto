import { type LatencyStages } from '@/hooks/useMetrics'

interface LatencyWaterfallProps {
  stages: LatencyStages | null
  p50_ms: number
  p95_ms: number
  sampleCount: number
}

interface StageConfig {
  key: string
  label: string
  sublabel: string
  barColor: string
  textColor: string
  dotColor: string
  p50Key: keyof LatencyStages
  p95Key: keyof LatencyStages
}

const STAGE_CONFIGS: StageConfig[] = [
  {
    key:      'parse',
    label:    'Parse',
    sublabel: 'WS → Normalize',
    barColor: 'bg-sky-500',
    textColor: 'text-sky-400',
    dotColor: 'bg-sky-500',
    p50Key:   'parse_p50_ms',
    p95Key:   'parse_p95_ms',
  },
  {
    key:      'scan',
    label:    'Scan',
    sublabel: 'Normalize → Scanner',
    barColor: 'bg-amber-500',
    textColor: 'text-amber-400',
    dotColor: 'bg-amber-500',
    p50Key:   'scan_p50_ms',
    p95Key:   'scan_p95_ms',
  },
  {
    key:      'decision',
    label:    'Decision',
    sublabel: 'Scanner → Trade',
    barColor: 'bg-violet-500',
    textColor: 'text-violet-400',
    dotColor: 'bg-violet-500',
    p50Key:   'decision_p50_ms',
    p95Key:   'decision_p95_ms',
  },
]

function fmt(ms: number | null | undefined): string {
  if (ms == null) return '—'
  if (ms < 1) return `${(ms * 1000).toFixed(0)}µs`
  return `${ms.toFixed(1)}ms`
}

function totalColor(ms: number): string {
  if (ms < 50)  return 'text-green-400'
  if (ms < 150) return 'text-yellow-400'
  return 'text-red-400'
}

export function LatencyWaterfall({ stages, p50_ms, p95_ms, sampleCount }: LatencyWaterfallProps) {
  const hasStages = stages !== null && stages?.parse_p50_ms != null

  const parseMs    = stages?.parse_p50_ms    ?? 0
  const scanMs     = stages?.scan_p50_ms     ?? 0
  const decisionMs = stages?.decision_p50_ms ?? 0
  const stageTotal = parseMs + scanMs + decisionMs || 1

  function widthPct(ms: number): string {
    return `${((ms / stageTotal) * 100).toFixed(1)}%`
  }

  return (
    <div className="rounded-lg border border-white/10 bg-gray-900 p-4">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-gray-400 uppercase tracking-wide">
          Pipeline Latency Breakdown
        </h3>
        <div className="flex items-center gap-4 text-xs">
          <span className="text-gray-600">
            {sampleCount > 0
              ? `${sampleCount.toLocaleString('en-US')} samples`
              : 'Awaiting data'}
          </span>
          {p50_ms > 0 && (
            <span className="font-mono">
              <span className={`font-semibold ${totalColor(p50_ms)}`}>{fmt(p50_ms)}</span>
              <span className="text-gray-600 mx-1">p50</span>
              <span className="text-gray-400">{fmt(p95_ms)}</span>
              <span className="text-gray-600 ml-1">p95</span>
            </span>
          )}
        </div>
      </div>

      {/* Stacked waterfall bar */}
      <div className="flex h-8 rounded-md overflow-hidden mb-1 gap-px bg-white/5">
        {hasStages ? (
          <>
            {/* Parse segment */}
            <div
              className="bg-sky-500/75 flex items-center justify-center shrink-0 transition-all duration-700"
              style={{ width: widthPct(parseMs) }}
              title={`Parse p50: ${fmt(stages?.parse_p50_ms)}`}
            >
              {parseMs / stageTotal > 0.12 && (
                <span className="text-xs font-mono text-white/90 px-1 truncate">
                  {fmt(stages?.parse_p50_ms)}
                </span>
              )}
            </div>
            {/* Scan segment */}
            <div
              className="bg-amber-500/75 flex items-center justify-center shrink-0 transition-all duration-700"
              style={{ width: widthPct(scanMs) }}
              title={`Scan p50: ${fmt(stages?.scan_p50_ms)}`}
            >
              {scanMs / stageTotal > 0.12 && (
                <span className="text-xs font-mono text-white/90 px-1 truncate">
                  {fmt(stages?.scan_p50_ms)}
                </span>
              )}
            </div>
            {/* Decision segment */}
            <div
              className="bg-violet-500/75 flex items-center justify-center min-w-0 flex-1 transition-all duration-700"
              title={`Decision p50: ${fmt(stages?.decision_p50_ms)}`}
            >
              {decisionMs / stageTotal > 0.12 && (
                <span className="text-xs font-mono text-white/90 px-1 truncate">
                  {fmt(stages?.decision_p50_ms)}
                </span>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <span className="text-xs text-gray-600 animate-pulse">
              Waiting for pipeline events…
            </span>
          </div>
        )}
      </div>

      {/* Stage axis labels */}
      {hasStages && (
        <div className="flex text-xs text-gray-600 mb-4 gap-px select-none">
          <div className="truncate transition-all duration-700" style={{ width: widthPct(parseMs) }}>
            WS→Norm
          </div>
          <div className="truncate transition-all duration-700" style={{ width: widthPct(scanMs) }}>
            Norm→Scan
          </div>
          <div className="flex-1 truncate">Scan→Dec</div>
        </div>
      )}

      {/* Per-stage rows with p50 / p95 */}
      <div className="space-y-2.5 mt-3">
        {STAGE_CONFIGS.map(stage => {
          const p50 = stages?.[stage.p50Key] ?? null
          const p95 = stages?.[stage.p95Key] ?? null
          const barWidth = stageTotal > 0 ? ((p50 ?? 0) / stageTotal) * 100 : 0

          return (
            <div key={stage.key} className="flex items-center gap-3">
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${stage.dotColor}`} />

              <div className="w-28 flex-shrink-0">
                <div className={`text-xs font-semibold leading-tight ${stage.textColor}`}>
                  {stage.label}
                </div>
                <div className="text-xs text-gray-600 leading-tight">{stage.sublabel}</div>
              </div>

              {/* Progress bar relative to total pipeline */}
              <div className="flex-1 h-1.5 bg-white/5 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${stage.barColor} opacity-60 transition-all duration-700`}
                  style={{ width: `${Math.min(barWidth, 100)}%` }}
                />
              </div>

              {/* p50 / p95 values */}
              <div className="w-28 flex-shrink-0 text-right font-mono text-xs">
                <span className="text-gray-200">{fmt(p50)}</span>
                <span className="text-gray-600 mx-1">/</span>
                <span className="text-gray-500">{fmt(p95)}</span>
              </div>
            </div>
          )
        })}
      </div>

      {/* Legend */}
      <div className="flex justify-end gap-4 mt-3 pt-2 border-t border-white/5 text-xs text-gray-600">
        <span><span className="text-gray-300 font-mono">A</span> = p50 median</span>
        <span><span className="text-gray-500 font-mono">B</span> = p95 tail</span>
      </div>
    </div>
  )
}
