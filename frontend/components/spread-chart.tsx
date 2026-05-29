'use client'

import { useEffect, useRef } from 'react'
import type { SpreadCandle, PnlPoint } from '@/lib/mock-data'
import type { UTCTimestamp } from 'lightweight-charts'

interface SpreadChartProps {
  spreadData: SpreadCandle[]
  pnlData: PnlPoint[]
}

function computeStats(candles: SpreadCandle[]): { mu: number; sigma: number } {
  if (candles.length === 0) return { mu: 0, sigma: 0 }
  const closes = candles.map(c => c.close)
  const mu = closes.reduce((s, v) => s + v, 0) / closes.length
  const variance = closes.reduce((s, v) => s + (v - mu) ** 2, 0) / closes.length
  return { mu, sigma: Math.sqrt(variance) }
}

export function SpreadChart({ spreadData, pnlData }: SpreadChartProps) {
  const spreadContainerRef = useRef<HTMLDivElement>(null)
  const pnlContainerRef = useRef<HTMLDivElement>(null)

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const spreadChartRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const spreadSeriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const muSeriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const upperSeriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const lowerSeriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pnlChartRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const pnlSeriesRef = useRef<any>(null)

  const spreadPrevLenRef = useRef(0)
  const pnlPrevLenRef = useRef(0)
  const pendingSpreadRef = useRef<SpreadCandle[]>([])
  const pendingPnlRef = useRef<PnlPoint[]>([])

  // Create both charts on mount
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!spreadContainerRef.current || !pnlContainerRef.current) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let spreadChart: any = null
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let pnlChart: any = null
    let removeListeners: (() => void) | undefined

    void import('lightweight-charts').then(({ createChart, ColorType, CandlestickSeries, AreaSeries, LineSeries, LineStyle }) => {
      if (!spreadContainerRef.current || !pnlContainerRef.current) return

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
        timeScale: {
          borderColor: 'rgba(255,255,255,0.08)',
          timeVisible: true,
          secondsVisible: false,
        },
      }

      // Spread candlestick chart
      spreadChart = createChart(spreadContainerRef.current, {
        ...sharedLayout,
        width: spreadContainerRef.current.clientWidth,
        height: 280,
      })

      const spreadSeries = spreadChart.addSeries(CandlestickSeries, {
        upColor: '#10b981',
        downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
      })

      const sharedBandOpts = {
        lineWidth: 1 as const,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      }

      const muSeries = spreadChart.addSeries(LineSeries, {
        ...sharedBandOpts,
        color: 'rgba(250, 204, 21, 0.7)',
        lineStyle: LineStyle.Solid,
      })

      const upperSeries = spreadChart.addSeries(LineSeries, {
        ...sharedBandOpts,
        color: 'rgba(96, 165, 250, 0.55)',
        lineStyle: LineStyle.Dotted,
      })

      const lowerSeries = spreadChart.addSeries(LineSeries, {
        ...sharedBandOpts,
        color: 'rgba(96, 165, 250, 0.55)',
        lineStyle: LineStyle.Dotted,
      })

      spreadChartRef.current = spreadChart
      spreadSeriesRef.current = spreadSeries
      muSeriesRef.current = muSeries
      upperSeriesRef.current = upperSeries
      lowerSeriesRef.current = lowerSeries

      // Apply any pending data that arrived before the chart loaded
      const pendingSpread = pendingSpreadRef.current
      if (pendingSpread.length > 0) {
        spreadSeries.setData(
          pendingSpread.map(c => ({
            time: c.time as UTCTimestamp,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
          }))
        )
        const { mu, sigma } = computeStats(pendingSpread)
        const bandData = pendingSpread.map(c => ({ time: c.time as UTCTimestamp, value: mu }))
        muSeries.setData(bandData)
        upperSeries.setData(pendingSpread.map(c => ({ time: c.time as UTCTimestamp, value: mu + 2 * sigma })))
        lowerSeries.setData(pendingSpread.map(c => ({ time: c.time as UTCTimestamp, value: mu - 2 * sigma })))
        spreadChart.timeScale().fitContent()
        spreadPrevLenRef.current = pendingSpread.length
      }

      // P&L area chart
      pnlChart = createChart(pnlContainerRef.current, {
        ...sharedLayout,
        width: pnlContainerRef.current.clientWidth,
        height: 140,
      })

      const pnlSeries = pnlChart.addSeries(AreaSeries, {
        lineColor: '#6366f1',
        topColor: 'rgba(99,102,241,0.18)',
        bottomColor: 'rgba(99,102,241,0.01)',
        lineWidth: 2,
        autoscaleInfoProvider: (
          original: () => { priceRange: { minValue: number; maxValue: number }; margins?: { above: number; below: number } } | null
        ) => {
          const res = original()
          if (res === null) return null
          return {
            priceRange: { minValue: 0, maxValue: res.priceRange.maxValue },
            margins: res.margins,
          }
        },
      })

      pnlChartRef.current = pnlChart
      pnlSeriesRef.current = pnlSeries

      const pendingPnl = pendingPnlRef.current
      if (pendingPnl.length > 0) {
        pnlSeries.setData(pendingPnl.map(p => ({ time: p.time as UTCTimestamp, value: p.value })))
        pnlChart.timeScale().fitContent()
        pnlPrevLenRef.current = pendingPnl.length
      }

      // Shared resize handler
      const handleResize = () => {
        if (spreadChart && spreadContainerRef.current) {
          spreadChart.applyOptions({ width: spreadContainerRef.current.clientWidth })
        }
        if (pnlChart && pnlContainerRef.current) {
          pnlChart.applyOptions({ width: pnlContainerRef.current.clientWidth })
        }
      }
      window.addEventListener('resize', handleResize)
      removeListeners = () => window.removeEventListener('resize', handleResize)
    })

    return () => {
      removeListeners?.()
      spreadChartRef.current = null
      spreadSeriesRef.current = null
      muSeriesRef.current = null
      upperSeriesRef.current = null
      lowerSeriesRef.current = null
      pnlChartRef.current = null
      pnlSeriesRef.current = null
      spreadPrevLenRef.current = 0
      pnlPrevLenRef.current = 0
      spreadChart?.remove()
      pnlChart?.remove()
    }
  }, [])

  // Incremental spread candle updates (candlestick + μ/±2σ bands)
  useEffect(() => {
    pendingSpreadRef.current = spreadData
    const series = spreadSeriesRef.current
    const chart = spreadChartRef.current
    const muS = muSeriesRef.current
    const upperS = upperSeriesRef.current
    const lowerS = lowerSeriesRef.current
    if (!series || !chart || spreadData.length === 0) return

    const prevLen = spreadPrevLenRef.current
    const { mu, sigma } = computeStats(spreadData)

    const setBands = () => {
      if (!muS || !upperS || !lowerS) return
      const muData = spreadData.map(c => ({ time: c.time as UTCTimestamp, value: mu }))
      muS.setData(muData)
      upperS.setData(spreadData.map(c => ({ time: c.time as UTCTimestamp, value: mu + 2 * sigma })))
      lowerS.setData(spreadData.map(c => ({ time: c.time as UTCTimestamp, value: mu - 2 * sigma })))
    }

    if (prevLen === 0 || spreadData.length < prevLen) {
      series.setData(
        spreadData.map(c => ({
          time: c.time as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))
      )
      setBands()
      chart.timeScale().fitContent()
    } else {
      // Last candle may have been updated in-place (same time key)
      const lastCandle = spreadData[spreadData.length - 1]
      series.update({
        time: lastCandle.time as UTCTimestamp,
        open: lastCandle.open,
        high: lastCandle.high,
        low: lastCandle.low,
        close: lastCandle.close,
      })
      // Recompute bands on every tick — mu/sigma shift as new data arrives
      setBands()
      if (spreadData.length > prevLen) {
        chart.timeScale().scrollToRealTime()
      }
    }
    spreadPrevLenRef.current = spreadData.length
  }, [spreadData])

  // Incremental P&L updates
  useEffect(() => {
    pendingPnlRef.current = pnlData
    const series = pnlSeriesRef.current
    const chart = pnlChartRef.current
    if (!series || !chart || pnlData.length === 0) return

    const prevLen = pnlPrevLenRef.current

    if (prevLen === 0 || pnlData.length < prevLen) {
      series.setData(pnlData.map(p => ({ time: p.time as UTCTimestamp, value: p.value })))
      chart.timeScale().fitContent()
    } else if (pnlData.length > prevLen) {
      for (const p of pnlData.slice(prevLen)) {
        series.update({ time: p.time as UTCTimestamp, value: p.value })
      }
      chart.timeScale().scrollToRealTime()
    }
    pnlPrevLenRef.current = pnlData.length
  }, [pnlData])

  return (
    <div className="space-y-4">
      <div>
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Spread BTC: Binance vs Kraken
          </p>
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs bg-black/40 backdrop-blur-sm border border-white/5">
              <span className="w-4 h-px bg-yellow-400 inline-block flex-shrink-0" />
              <span className="text-gray-400 whitespace-nowrap">μ (media del spread)</span>
            </span>
            <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs bg-black/40 backdrop-blur-sm border border-white/5">
              <span className="inline-block w-4 flex-shrink-0 border-t-2 border-dotted border-blue-400" />
              <span className="text-gray-400 whitespace-nowrap">±2σ (banda estadística)</span>
            </span>
            <span className="inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs bg-black/40 backdrop-blur-sm border border-white/5">
              <span className="inline-flex gap-0.5">
                <span className="w-2 h-3 rounded-sm bg-emerald-500 inline-block" />
                <span className="w-2 h-3 rounded-sm bg-red-500 inline-block" />
              </span>
              <span className="text-gray-400 whitespace-nowrap">Spread actual</span>
            </span>
          </div>
        </div>
        <div ref={spreadContainerRef} className="w-full" style={{ height: '280px' }} />
      </div>
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500 mb-2">
          Cumulative P&amp;L
        </p>
        <div ref={pnlContainerRef} className="w-full" style={{ height: '140px' }} />
      </div>
    </div>
  )
}
