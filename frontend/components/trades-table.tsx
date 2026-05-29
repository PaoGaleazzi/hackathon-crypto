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

const STATUS_STYLES: Record<TradeStatus, string> = {
  EXECUTED: 'bg-green-500/15 text-green-400 border-green-500/30',
  PARTIAL_FILL: 'bg-yellow-500/15 text-yellow-400 border-yellow-500/30',
  ABORTED_STALE: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
}

const STATUS_LABELS: Record<TradeStatus, string> = {
  EXECUTED: 'Executed',
  PARTIAL_FILL: 'Partial',
  ABORTED_STALE: 'Stale',
}

function fillColor(ratio: number): string {
  if (ratio >= 0.9) return 'text-green-400'
  if (ratio >= 0.7) return 'text-yellow-400'
  return 'text-red-400'
}

function formatPrice(value: number): string {
  return `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function formatUsd(value: number): string {
  const abs = Math.abs(value)
  const str = abs.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `-$${str}` : `$${str}`
}

export function TradesTable({ trades }: TradesTableProps) {
  const sorted = [...trades].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  )

  return (
    <div className="rounded-lg border border-white/10 overflow-hidden">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="border-white/10 hover:bg-transparent">
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">
                Route
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Qty BTC
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Buy Price
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Sell Price
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Fees
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Slippage
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Net USDT
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Fill%
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide text-right">
                Time
              </TableHead>
              <TableHead className="text-gray-400 text-xs uppercase tracking-wide">
                Status
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((trade) => (
              <TableRow
                key={trade.id}
                className="border-white/5 hover:bg-white/5 transition-colors"
              >
                <TableCell className="text-sm font-medium text-gray-200 whitespace-nowrap">
                  {trade.exchange_buy}{' '}
                  <span className="text-gray-500 mx-1">→</span>{' '}
                  {trade.exchange_sell}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-300">
                  {trade.qty_btc.toFixed(3)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-300 whitespace-nowrap">
                  {formatPrice(trade.price_buy)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-300 whitespace-nowrap">
                  {formatPrice(trade.price_sell)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-400">
                  {formatUsd(trade.fee_total_usdt)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-400">
                  {formatUsd(trade.slippage_usdt)}
                </TableCell>
                <TableCell className="text-sm text-right font-mono font-semibold text-green-400">
                  {formatUsd(trade.net_usdt)}
                </TableCell>
                <TableCell className={`text-sm text-right font-mono font-medium ${fillColor(trade.fill_ratio)}`}>
                  {(trade.fill_ratio * 100).toFixed(0)}%
                </TableCell>
                <TableCell className="text-sm text-right font-mono text-gray-400 whitespace-nowrap">
                  {format(parseISO(trade.timestamp), 'HH:mm:ss')}
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
