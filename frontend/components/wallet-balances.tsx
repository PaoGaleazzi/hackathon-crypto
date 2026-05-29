import { type Trade } from '@/lib/mock-data'

interface WalletBalancesProps {
  trades: Trade[]
}

interface Balance {
  exchange: string
  label: string
  usdt: number
  btc: number
}

const EXCHANGES = ['binance', 'kraken', 'coinbase', 'okx'] as const
const EXCHANGE_LABELS: Record<string, string> = {
  binance: 'Binance',
  kraken: 'Kraken',
  coinbase: 'Coinbase',
  okx: 'OKX',
}

const INITIAL_USDT = 10_000
const INITIAL_BTC = 0.5

function computeBalances(trades: Trade[]): Balance[] {
  const usdt: Record<string, number> = {}
  const btc: Record<string, number> = {}
  for (const ex of EXCHANGES) {
    usdt[ex] = INITIAL_USDT
    btc[ex] = INITIAL_BTC
  }

  for (const t of trades) {
    if (t.status !== 'EXECUTED') continue
    const buy = t.buy_exchange.toLowerCase()
    const sell = t.sell_exchange.toLowerCase()
    if (usdt[buy] !== undefined) {
      usdt[buy] -= t.buy_price * t.qty + t.fee_buy
      btc[buy] += t.qty
    }
    if (btc[sell] !== undefined) {
      btc[sell] -= t.qty
      usdt[sell] += t.sell_price * t.qty - t.fee_sell
    }
  }

  return EXCHANGES.map(ex => ({
    exchange: ex,
    label: EXCHANGE_LABELS[ex],
    usdt: usdt[ex],
    btc: btc[ex],
  }))
}

function usdtColor(usdt: number): string {
  if (usdt >= 10_000) return 'text-gray-300'
  if (usdt >= 9_500) return 'text-yellow-400'
  return 'text-red-400'
}

export function WalletBalances({ trades }: WalletBalancesProps) {
  const balances = computeBalances(trades)

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {balances.map(b => (
        <div
          key={b.exchange}
          className="rounded-lg border border-white/10 bg-gray-900 p-3"
        >
          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
            {b.label}
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-600">USDT</span>
              <span className={`text-sm font-mono font-semibold ${usdtColor(b.usdt)}`}>
                {b.usdt.toLocaleString('en-US', {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-gray-600">BTC</span>
              <span className="text-sm font-mono font-semibold text-orange-300">
                {b.btc.toFixed(4)}
              </span>
            </div>
          </div>
          {/* USDT progress bar relative to initial */}
          <div className="mt-2 h-1 rounded-full bg-white/5 overflow-hidden">
            <div
              className="h-full rounded-full bg-blue-500/50 transition-all duration-500"
              style={{ width: `${Math.min(100, Math.max(0, (b.usdt / INITIAL_USDT) * 100))}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}
