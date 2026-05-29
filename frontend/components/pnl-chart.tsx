'use client'

import { useEffect, useRef } from 'react'
import { type PnlPoint } from '@/lib/mock-data'
import type { UTCTimestamp } from 'lightweight-charts'

interface PnlChartProps {
  data: PnlPoint[]
}

export function PnlChart({ data }: PnlChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (!containerRef.current) return

    let chart: import('lightweight-charts').IChartApi | null = null
    let removeListener: (() => void) | undefined

    // Dynamic import avoids SSR issues with browser-only APIs
    void import('lightweight-charts').then(({ createChart, ColorType, AreaSeries }) => {
      if (!containerRef.current) return

      chart = createChart(containerRef.current, {
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
        rightPriceScale: {
          borderColor: 'rgba(255,255,255,0.1)',
        },
        timeScale: {
          borderColor: 'rgba(255,255,255,0.1)',
          timeVisible: true,
          secondsVisible: false,
        },
      })

      const series = chart.addSeries(AreaSeries, {
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

      // UTCTimestamp is a nominal number type — values are already Unix seconds
      series.setData(
        data.map((p) => ({
          time: p.time as UTCTimestamp,
          value: p.value,
        }))
      )

      chart.timeScale().fitContent()

      const handleResize = () => {
        if (chart && containerRef.current) {
          chart.applyOptions({ width: containerRef.current.clientWidth })
        }
      }

      window.addEventListener('resize', handleResize)
      removeListener = () => window.removeEventListener('resize', handleResize)
    })

    return () => {
      removeListener?.()
      chart?.remove()
    }
  }, [data])

  return (
    <div
      ref={containerRef}
      className="w-full"
      style={{ height: '240px' }}
    />
  )
}
