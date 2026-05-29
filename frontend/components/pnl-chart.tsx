'use client'

import { useEffect, useRef } from 'react'
import { type PnlPoint } from '@/lib/mock-data'
import type { UTCTimestamp } from 'lightweight-charts'

interface PnlChartProps {
  data: PnlPoint[]
}

export function PnlChart({ data }: PnlChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const seriesRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chartRef = useRef<any>(null)
  const pendingDataRef = useRef<PnlPoint[]>([])
  const prevLenRef = useRef(0)

  // Create chart once on mount
  useEffect(() => {
    if (typeof window === 'undefined' || !containerRef.current) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    let chartInst: any = null
    let removeListener: (() => void) | undefined

    void import('lightweight-charts').then(({ createChart, ColorType, AreaSeries }) => {
      if (!containerRef.current) return

      chartInst = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 240,
        layout: {
          background: { type: ColorType.Solid, color: 'transparent' },
          textColor: '#9ca3af',
        },
        grid: {
          vertLines: { color: 'rgba(255,255,255,0.05)' },
          horzLines: { color: 'rgba(255,255,255,0.05)' },
        },
        crosshair: {
          vertLine: { color: 'rgba(255,255,255,0.3)' },
          horzLine: { color: 'rgba(255,255,255,0.3)' },
        },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' },
        timeScale: {
          borderColor: 'rgba(255,255,255,0.1)',
          timeVisible: true,
          secondsVisible: false,
        },
      })

      const series = chartInst.addSeries(AreaSeries, {
        lineColor: '#22c55e',
        topColor: 'rgba(34, 197, 94, 0.25)',
        bottomColor: 'rgba(34, 197, 94, 0.02)',
        lineWidth: 2,
        priceFormat: {
          type: 'custom',
          formatter: (price: number) =>
            `$${price.toLocaleString('en-US', {
              minimumFractionDigits: 0,
              maximumFractionDigits: 0,
            })}`,
          minMove: 1,
        },
      })

      chartRef.current = chartInst
      seriesRef.current = series

      // Apply any data that arrived before chart finished loading
      const pending = pendingDataRef.current
      if (pending.length > 0) {
        series.setData(pending.map(p => ({ time: p.time as UTCTimestamp, value: p.value })))
        chartInst.timeScale().fitContent()
        prevLenRef.current = pending.length
      }

      const handleResize = () => {
        if (chartInst && containerRef.current) {
          chartInst.applyOptions({ width: containerRef.current.clientWidth })
        }
      }
      window.addEventListener('resize', handleResize)
      removeListener = () => window.removeEventListener('resize', handleResize)
    })

    return () => {
      removeListener?.()
      chartRef.current = null
      seriesRef.current = null
      prevLenRef.current = 0
      chartInst?.remove()
    }
  }, []) // mount only — chart is never destroyed unless component unmounts

  // Incremental data updates — no chart destroy/recreate
  useEffect(() => {
    pendingDataRef.current = data
    const series = seriesRef.current
    const chart = chartRef.current
    if (!series || !chart || data.length === 0) return

    const prevLen = prevLenRef.current

    if (prevLen === 0 || data.length < prevLen) {
      // Full reset: initial load or data source switched
      series.setData(data.map(p => ({ time: p.time as UTCTimestamp, value: p.value })))
      chart.timeScale().fitContent()
    } else if (data.length > prevLen) {
      // Incremental: append only new points, no visual flash
      for (const p of data.slice(prevLen)) {
        series.update({ time: p.time as UTCTimestamp, value: p.value })
      }
      chart.timeScale().scrollToRealTime()
    }
    prevLenRef.current = data.length
  }, [data])

  return (
    <div
      ref={containerRef}
      className="w-full"
      style={{ height: '240px' }}
    />
  )
}
