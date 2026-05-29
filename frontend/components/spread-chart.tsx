'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import type { SpreadCandle, PnlPoint } from '@/lib/mock-data'
import type { UTCTimestamp } from 'lightweight-charts'

// ── types ────────────────────────────────────────────────────────────────────

type Timeframe = '5s' | '15s' | '1m' | '5m'
const TF_SECONDS: Record<Timeframe, number> = { '5s': 5, '15s': 15, '1m': 60, '5m': 300 }
const TIMEFRAMES: Timeframe[] = ['5s', '15s', '1m', '5m']

interface SpreadChartProps {
  spreadData: SpreadCandle[]
  pnlData: PnlPoint[] // kept for backward compat — volume panel replaces P&L
}

// ── helpers ──────────────────────────────────────────────────────────────────

function aggregateCandles(raw: SpreadCandle[], bucketSec: number): SpreadCandle[] {
  if (raw.length === 0) return []
  const map = new Map<number, SpreadCandle>()
  for (const c of raw) {
    const key = Math.floor(c.time / bucketSec) * bucketSec
    const ex = map.get(key)
    if (!ex) {
      map.set(key, { time: key, open: c.open, high: c.high, low: c.low, close: c.close })
    } else {
      ex.high = Math.max(ex.high, c.high)
      ex.low = Math.min(ex.low, c.low)
      ex.close = c.close
    }
  }
  return Array.from(map.values()).sort((a, b) => a.time - b.time)
}

function computeStats(candles: SpreadCandle[]): { mu: number; sigma: number } {
  if (candles.length === 0) return { mu: 0, sigma: 0 }
  const closes = candles.map(c => c.close)
  const mu = closes.reduce((s, v) => s + v, 0) / closes.length
  const variance = closes.reduce((s, v) => s + (v - mu) ** 2, 0) / closes.length
  return { mu, sigma: Math.sqrt(variance) }
}

// ── component ─────────────────────────────────────────────────────────────────

export function SpreadChart({ spreadData }: SpreadChartProps) {
  const [timeframe, setTimeframe] = useState<Timeframe>('5s')

  // DOM refs
  const mainContainerRef = useRef<HTMLDivElement>(null)
  const volContainerRef  = useRef<HTMLDivElement>(null)

  // Chart refs (populated after async import)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mainChartRef   = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const spreadSeriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const muSeriesRef    = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const upperSeriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const lowerSeriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const volChartRef    = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const volSeriesRef   = useRef<any>(null)

  // Track previous state for incremental updates
  const prevTfRef  = useRef<Timeframe>('5s')
  const prevLenRef = useRef(0)

  // Latest candles ref so chart-creation callback can seed initial data
  const latestCandlesRef = useRef<SpreadCandle[]>([])
  const latestTfRef      = useRef<Timeframe>('5s')

  // Aggregated candles — recomputed when spreadData or timeframe changes
  const candles = useMemo(
    () => aggregateCandles(spreadData, TF_SECONDS[timeframe]),
    [spreadData, timeframe],
  )

  // Keep latest refs current
  useEffect(() => {
    latestCandlesRef.current = candles
    latestTfRef.current = timeframe
  }, [candles, timeframe])

  // ── chart creation (mount only) ──────────────────────────────────────────

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!mainContainerRef.current || !volContainerRef.current) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let mainChart: any = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let volChart: any = null
    let removeListeners: (() => void) | undefined

    void import('lightweight-charts').then(({
      createChart,
      ColorType,
      CandlestickSeries,
      LineSeries,
      LineStyle,
      HistogramSeries,
    }) => {
      if (!mainContainerRef.current || !volContainerRef.current) return

      const sharedLayout = {
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: '#6b7280',
        },
        grid: {
          vertLines: { color: 'rgba(255,255,255,0.04)' },
          horzLines: { color: 'rgba(255,255,255,0.04)' },
        },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.08)' },
        crosshair: { mode: 1 }, // Normal mode
      }

      // ── Main chart (top, ~70%) ───────────────────────────────────────────

      mainChart = createChart(mainContainerRef.current, {
        ...sharedLayout,
        width: mainContainerRef.current.clientWidth,
        height: mainContainerRef.current.clientHeight,
        timeScale: {
          borderColor: 'rgba(255,255,255,0.08)',
          timeVisible: true,
          secondsVisible: true,
          // Hide time labels on main chart — shown only on vol chart below
          fixLeftEdge: false,
          fixRightEdge: false,
        },
      })

      const spreadSeries = mainChart.addSeries(CandlestickSeries, {
        upColor: '#10b981',
        downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
        lastValueVisible: true,
        priceLineVisible: true,
        priceLineColor: 'rgba(107,114,128,0.6)',
        priceLineWidth: 1,
        priceLineStyle: LineStyle.Dotted,
      })

      const bandOpts = {
        lineWidth: 1 as const,
        priceLineVisible: false,
        lastValueVisible: true,
        crosshairMarkerVisible: false,
      }

      const muSeries = mainChart.addSeries(LineSeries, {
        ...bandOpts,
        color: 'rgba(250, 204, 21, 0.7)',
        lineStyle: LineStyle.Solid,
        title: 'μ',
      })

      const upperSeries = mainChart.addSeries(LineSeries, {
        ...bandOpts,
        color: 'rgba(96, 165, 250, 0.55)',
        lineStyle: LineStyle.Dotted,
        title: '+2σ',
      })

      const lowerSeries = mainChart.addSeries(LineSeries, {
        ...bandOpts,
        color: 'rgba(96, 165, 250, 0.55)',
        lineStyle: LineStyle.Dotted,
        title: '-2σ',
      })

      mainChartRef.current    = mainChart
      spreadSeriesRef.current = spreadSeries
      muSeriesRef.current     = muSeries
      upperSeriesRef.current  = upperSeries
      lowerSeriesRef.current  = lowerSeries

      // ── Volume chart (bottom, ~30%) ──────────────────────────────────────

      volChart = createChart(volContainerRef.current, {
        ...sharedLayout,
        width: volContainerRef.current.clientWidth,
        height: volContainerRef.current.clientHeight,
        timeScale: {
          borderColor: 'rgba(255,255,255,0.08)',
          timeVisible: true,
          secondsVisible: true,
        },
        rightPriceScale: {
          borderColor: 'rgba(255,255,255,0.08)',
          scaleMargins: { top: 0.1, bottom: 0 },
        },
      })

      const volSeries = volChart.addSeries(HistogramSeries, {
        color: 'rgba(16,185,129,0.6)',
        priceFormat: { type: 'volume' as const },
        priceScaleId: 'right',
        priceLineVisible: false,
        lastValueVisible: false,
      })

      volChartRef.current  = volChart
      volSeriesRef.current = volSeries

      // ── Seed initial data ────────────────────────────────────────────────

      const init = latestCandlesRef.current
      if (init.length > 0) {
        const { mu, sigma } = computeStats(init)
        spreadSeries.setData(init.map(c => ({
          time: c.time as UTCTimestamp,
          open: c.open, high: c.high, low: c.low, close: c.close,
        })))
        muSeries.setData(init.map(c => ({ time: c.time as UTCTimestamp, value: mu })))
        upperSeries.setData(init.map(c => ({ time: c.time as UTCTimestamp, value: mu + 2 * sigma })))
        lowerSeries.setData(init.map(c => ({ time: c.time as UTCTimestamp, value: mu - 2 * sigma })))
        volSeries.setData(init.map(c => ({
          time: c.time as UTCTimestamp,
          value: c.high - c.low,
          color: c.close >= c.open ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)',
        })))
        mainChart.timeScale().fitContent()
        volChart.timeScale().fitContent()
        prevLenRef.current = init.length
        prevTfRef.current  = latestTfRef.current
      }

      // ── Crosshair sync ───────────────────────────────────────────────────

      let xSyncing = false

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      mainChart.subscribeCrosshairMove((param: any) => {
        if (xSyncing || !volChartRef.current || !volSeriesRef.current) return
        xSyncing = true
        if (!param.time) {
          volChartRef.current.clearCrosshairPosition()
        } else {
          volChartRef.current.setCrosshairPosition(0, param.time, volSeriesRef.current)
        }
        xSyncing = false
      })

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      volChart.subscribeCrosshairMove((param: any) => {
        if (xSyncing || !mainChartRef.current || !spreadSeriesRef.current) return
        xSyncing = true
        if (!param.time) {
          mainChartRef.current.clearCrosshairPosition()
        } else {
          mainChartRef.current.setCrosshairPosition(0, param.time, spreadSeriesRef.current)
        }
        xSyncing = false
      })

      // ── Time-scale sync (zoom/pan) ───────────────────────────────────────

      let tsSyncing = false

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      mainChart.timeScale().subscribeVisibleLogicalRangeChange((range: any) => {
        if (tsSyncing || !volChartRef.current || !range) return
        tsSyncing = true
        volChartRef.current.timeScale().setVisibleLogicalRange(range)
        tsSyncing = false
      })

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      volChart.timeScale().subscribeVisibleLogicalRangeChange((range: any) => {
        if (tsSyncing || !mainChartRef.current || !range) return
        tsSyncing = true
        mainChartRef.current.timeScale().setVisibleLogicalRange(range)
        tsSyncing = false
      })

      // ── Resize ───────────────────────────────────────────────────────────

      const handleResize = () => {
        if (mainChart && mainContainerRef.current) {
          mainChart.applyOptions({ width: mainContainerRef.current.clientWidth })
        }
        if (volChart && volContainerRef.current) {
          volChart.applyOptions({ width: volContainerRef.current.clientWidth })
        }
      }
      window.addEventListener('resize', handleResize)
      removeListeners = () => window.removeEventListener('resize', handleResize)
    })

    return () => {
      removeListeners?.()
      mainChartRef.current    = null
      spreadSeriesRef.current = null
      muSeriesRef.current     = null
      upperSeriesRef.current  = null
      lowerSeriesRef.current  = null
      volChartRef.current     = null
      volSeriesRef.current    = null
      prevLenRef.current      = 0
      prevTfRef.current       = '5s'
      mainChart?.remove()
      volChart?.remove()
    }
  }, [])

  // ── Data updates ─────────────────────────────────────────────────────────

  useEffect(() => {
    const series  = spreadSeriesRef.current
    const chart   = mainChartRef.current
    const muS     = muSeriesRef.current
    const upperS  = upperSeriesRef.current
    const lowerS  = lowerSeriesRef.current
    const volS    = volSeriesRef.current
    const volC    = volChartRef.current
    if (!series || !chart || candles.length === 0) return

    const { mu, sigma } = computeStats(candles)
    const tfChanged    = timeframe !== prevTfRef.current
    const isFirstLoad  = prevLenRef.current === 0
    const needFullReset = tfChanged || isFirstLoad

    const toCandle = (c: SpreadCandle) => ({
      time: c.time as UTCTimestamp,
      open: c.open, high: c.high, low: c.low, close: c.close,
    })

    const toVolBar = (c: SpreadCandle) => ({
      time: c.time as UTCTimestamp,
      value: c.high - c.low,
      color: c.close >= c.open ? 'rgba(16,185,129,0.6)' : 'rgba(239,68,68,0.6)',
    })

    if (needFullReset) {
      series.setData(candles.map(toCandle))
      if (muS)    muS.setData(candles.map(c => ({ time: c.time as UTCTimestamp, value: mu })))
      if (upperS) upperS.setData(candles.map(c => ({ time: c.time as UTCTimestamp, value: mu + 2 * sigma })))
      if (lowerS) lowerS.setData(candles.map(c => ({ time: c.time as UTCTimestamp, value: mu - 2 * sigma })))
      if (volS)   volS.setData(candles.map(toVolBar))
      chart.timeScale().fitContent()
      if (volC) volC.timeScale().fitContent()
    } else {
      // Incremental: update last candle (handles in-place tick or new candle)
      const last = candles[candles.length - 1]
      series.update(toCandle(last))
      if (volS) volS.update(toVolBar(last))

      // Bands must be recomputed as full arrays since mu/sigma shift each tick
      if (muS)    muS.setData(candles.map(c => ({ time: c.time as UTCTimestamp, value: mu })))
      if (upperS) upperS.setData(candles.map(c => ({ time: c.time as UTCTimestamp, value: mu + 2 * sigma })))
      if (lowerS) lowerS.setData(candles.map(c => ({ time: c.time as UTCTimestamp, value: mu - 2 * sigma })))

      if (candles.length > prevLenRef.current) {
        chart.timeScale().scrollToRealTime()
        if (volC) volC.timeScale().scrollToRealTime()
      }
    }

    prevTfRef.current  = timeframe
    prevLenRef.current = candles.length
  }, [candles, timeframe])

  // ── render ────────────────────────────────────────────────────────────────

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-3">
          <span className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Spread BTC — Binance / Kraken
          </span>

          {/* Timeframe picker */}
          <div
            className="flex items-center rounded overflow-hidden border"
            style={{ background: '#0d1117', borderColor: '#1f2937' }}
          >
            {TIMEFRAMES.map(tf => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className="px-2.5 py-1 text-[11px] font-mono font-semibold transition-colors"
                style={
                  tf === timeframe
                    ? { background: 'rgba(99,102,241,0.20)', color: '#a5b4fc' }
                    : { color: '#6b7280' }
                }
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-1.5">
          <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs border border-white/5" style={{ background: 'rgba(0,0,0,0.4)' }}>
            <span className="w-4 h-px bg-yellow-400 inline-block flex-shrink-0" />
            <span className="text-gray-400">μ</span>
          </span>
          <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs border border-white/5" style={{ background: 'rgba(0,0,0,0.4)' }}>
            <span className="inline-block w-4 border-t-2 border-dotted border-blue-400 flex-shrink-0" />
            <span className="text-gray-400">±2σ</span>
          </span>
          <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs border border-white/5" style={{ background: 'rgba(0,0,0,0.4)' }}>
            <span className="inline-flex gap-0.5">
              <span className="w-2 h-3 rounded-sm bg-emerald-500 inline-block" />
              <span className="w-2 h-3 rounded-sm bg-red-500 inline-block" />
            </span>
            <span className="text-gray-400">Spread</span>
          </span>
        </div>
      </div>

      {/* Main candlestick panel (70%) */}
      <div ref={mainContainerRef} className="w-full" style={{ height: '260px' }} />

      {/* Volume panel label */}
      <div className="flex items-center gap-2 mt-0.5 px-1" style={{ height: '18px' }}>
        <span className="text-[10px] uppercase tracking-wide text-gray-600">Range (high−low)</span>
      </div>

      {/* Volume / range panel (30%) */}
      <div ref={volContainerRef} className="w-full" style={{ height: '90px' }} />
    </div>
  )
}
