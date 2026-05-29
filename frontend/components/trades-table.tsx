'use client'

import { useEffect, useRef, useState } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { format, parseISO } from 'date-fns'
import { type Trade, type TradeStatus } from '@/lib/mock-data'

interface TradesTableProps {
  trades: Trade[]
}

const EXCHANGE_LABELS: Record<string, string> = {
  binance: 'Binance',
  kraken: 'Kraken',
  coinbase: 'Coinbase',
  okx: 'OKX',
}

const STATUS_STYLES: Record<TradeStatus, string> = {
  EXECUTED:                    'bg-green-500/15 text-green-400 border-green-500/30',
  ABORTED_STALE:               'bg-orange-500/15 text-orange-400 border-orange-500/30',
  SKIPPED_MIN_FILL:            'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  REJECTED_INSUFFICIENT_BALANCE: 'bg-red-500/15 text-red-400 border-red-500/30',
  REJECTED_NEGATIVE_NET:       'bg-red-500/15 text-red-400 border-red-500/30',
  CIRCUIT_BREAKER_OPEN:        'bg-purple-500/15 text-purple-400 border-purple-500/30',
}

const STATUS_LABELS: Record<TradeStatus, string> = {
  EXECUTED:                    'Executed',
  ABORTED_STALE:               'Stale',
  SKIPPED_MIN_FILL:            'Low Fill',
  REJECTED_INSUFFICIENT_BALANCE: 'No Balance',
  REJECTED_NEGATIVE_NET:       'Rejected',
  CIRCUIT_BREAKER_OPEN:        'CB Open',
}

function profitColor(value: number): string {
  if (value > 0) return 'text-green-400'
  if (value < 0) return 'text-red-400'
  return 'text-gray-400'
}

function formatPrice(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatUsd(value: number): string {
  const abs = Math.abs(value)
  const str = abs.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return value < 0 ? `-$${str}` : `$${str}`
}

function fmtEx(ex: string): string {
  return EXCHANGE_LABELS[ex?.toLowerCase()] ?? ex
}

export function TradesTable({ trades }: TradesTableProps) {
  const prevIdsRef = useRef<Set<string>>(new Set())
  const [flashIds, setFlashIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    const currentIds = new Set(trades.map(t => t.id))
    const newIds = [...currentIds].filter(id => !prevIdsRef.current.has(id))
    prevIdsRef.current = currentIds
    if (newIds.length === 0) return

    setFlashIds(prev => new Set([...prev, ...newIds]))
    const timer = setTimeout(() => {
      setFlashIds(prev => {
        const next = new Set(prev)
        newIds.forEach(id => next.delete(id))
        return next
      })
    }, 1500)
    return () => clearTimeout(timer)
  }, [trades])

  const unique = Array.from(new Map(trades.map(t => [t.id, t])).values())
  const sorted = unique.sort(
    (a, b) => new Date(b.executed_at).getTime() - new Date(a.executed_at).getTime()
  )

  return (
    <div className="rounded-lg border border-white/10 overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-white/10 hover:bg-transparent">
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">Route</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Qty BTC</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Buy Price</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Sell Price</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Fees</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Slippage</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Net USDT</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Latency</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">Time</TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((trade) => (
              <TableRow
                key={trade.id}
                className={`border-white/5 hover:bg-white/5 transition-colors ${flashIds.has(trade.id) ? 'row-flash' : ''}`}
              >
                <TableCell className="text-sm font-medium text-gray-200 whitespace-nowrap">
                  {fmtEx(trade.buy_exchange)}
                  <span className="text-gray-500 mx-1">→</span>
                  {fmtEx(trade.sell_exchange)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-300">
                  {trade.qty.toFixed(3)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-300 whitespace-nowrap">
                  {formatPrice(trade.buy_price)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-300 whitespace-nowrap">
                  {formatPrice(trade.sell_price)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-400">
                  {formatUsd(trade.fee_buy + trade.fee_sell)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-400">
                  {formatUsd(trade.slippage_est)}
                </TableCell>
                <TableCell className={`text-sm text-right font-mono font-semibold ${profitColor(trade.net_profit)}`}>
                  {formatUsd(trade.net_profit)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-400">
                  {trade.latency_ms.toFixed(1)}ms
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-400 whitespace-nowrap">
                  {format(parseISO(trade.executed_at), 'HH:mm:ss')}
                </TableCell>
                <TableCell>
                  <Badge
                    variant="outline"
                    className={`text-xs whitespace-nowrap ${STATUS_STYLES[trade.status]}`}
                  >
                    {STATUS_LABELS[trade.status]}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
