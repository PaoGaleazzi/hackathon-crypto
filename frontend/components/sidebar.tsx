'use client'

import {
  LayoutDashboard,
  TrendingUp,
  ArrowLeftRight,
  BarChart2,
  Settings,
  Zap,
} from 'lucide-react'

interface SidebarProps {
  activeView: string
  onNavigate: (view: string) => void
  circuitBreaker: 'OPEN' | 'CLOSED' | null
  botActive: boolean
  connected?: boolean
  uptimeS?: number
}

const NAV_ITEMS = [
  { id: 'dashboard',     label: 'Dashboard',     Icon: LayoutDashboard },
  { id: 'opportunities', label: 'Opportunities',  Icon: TrendingUp },
  { id: 'trades',        label: 'Trades',         Icon: ArrowLeftRight },
  { id: 'analytics',    label: 'Analytics',      Icon: BarChart2 },
  { id: 'settings',     label: 'Settings',       Icon: Settings },
]

function formatUptime(s: number): string {
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}

export function Sidebar({ activeView, onNavigate, circuitBreaker, botActive, connected = false, uptimeS = 0 }: SidebarProps) {
  const cbOpen = circuitBreaker === 'OPEN'

  return (
    <aside
      className="flex flex-col flex-shrink-0 w-14 sm:w-56 h-full border-r"
      style={{ background: '#0d1117', borderColor: '#1f2937' }}
    >
      {/* Logo */}
      <div className="flex items-center justify-center sm:justify-start gap-3 px-0 sm:px-4 py-5 border-b" style={{ borderColor: '#1f2937' }}>
        <div
          className="flex items-center justify-center w-9 h-9 rounded-lg flex-shrink-0"
          style={{ background: 'linear-gradient(135deg, #6366f1, #8b5cf6)' }}
        >
          <Zap className="w-5 h-5 text-white" />
        </div>
        <div className="hidden sm:block">
          <p className="text-sm font-bold text-white tracking-wide">ARB BOT</p>
          <p className="text-[10px] text-gray-500 leading-tight">BTC Multi-Exchange</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-1.5 sm:px-3 py-4 space-y-0.5">
        {NAV_ITEMS.map(({ id, label, Icon }) => {
          const isActive = activeView === id
          return (
            <button
              key={id}
              onClick={() => onNavigate(id)}
              title={label}
              className="relative flex items-center justify-center sm:justify-start gap-0 sm:gap-3 w-full px-0 sm:px-3 py-2.5 rounded-lg text-sm transition-colors"
              style={
                isActive
                  ? { background: 'rgba(99,102,241,0.12)', color: '#a5b4fc' }
                  : undefined
              }
              onMouseEnter={e => {
                if (!isActive) {
                  ;(e.currentTarget as HTMLButtonElement).style.color = '#d1d5db'
                  ;(e.currentTarget as HTMLButtonElement).style.background = 'rgba(255,255,255,0.05)'
                }
              }}
              onMouseLeave={e => {
                if (!isActive) {
                  ;(e.currentTarget as HTMLButtonElement).style.color = ''
                  ;(e.currentTarget as HTMLButtonElement).style.background = ''
                }
              }}
            >
              {isActive && (
                <span
                  className="hidden sm:block absolute left-2 top-1/2 -translate-y-1/2 w-1 h-1 rounded-full"
                  style={{ background: '#818cf8' }}
                />
              )}
              <Icon
                className="w-4 h-4 flex-shrink-0"
                style={isActive ? { color: '#818cf8' } : { color: '#6b7280' }}
              />
              <span className="hidden sm:block" style={isActive ? {} : { color: '#6b7280' }}>{label}</span>
            </button>
          )
        })}
      </nav>

      {/* Footer */}
      <div className="px-2 sm:px-4 py-4 border-t space-y-2.5" style={{ borderColor: '#1f2937' }}>
        {/* Version */}
        <div className="hidden sm:flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wide text-gray-600">Version</span>
          <span className="text-[10px] font-mono text-gray-500">v1.0.0</span>
        </div>

        {/* Uptime */}
        <div className="hidden sm:flex items-center justify-between">
          <span className="text-[10px] uppercase tracking-wide text-gray-600">Uptime</span>
          <span className="text-[10px] font-mono text-gray-400">
            {uptimeS > 0 ? formatUptime(uptimeS) : '—'}
          </span>
        </div>

        {/* Connection */}
        <div className="flex items-center justify-center sm:justify-between">
          <span className="hidden sm:block text-[10px] uppercase tracking-wide text-gray-600">Connection</span>
          <span
            className="flex items-center gap-1.5 text-[10px] font-medium"
            style={{ color: connected ? '#4ade80' : '#6b7280' }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ background: connected ? '#4ade80' : '#6b7280' }}
            />
            <span className="hidden sm:block">{connected ? 'LIVE' : 'OFFLINE'}</span>
          </span>
        </div>

        {/* Circuit breaker */}
        <div className="flex items-center justify-center sm:justify-between">
          <span className="hidden sm:block text-[10px] uppercase tracking-wide text-gray-600">Circuit breaker</span>
          <span
            className="flex items-center gap-1.5 text-[10px] font-medium"
            style={{ color: cbOpen ? '#f87171' : '#4ade80' }}
          >
            <span
              className="w-1.5 h-1.5 rounded-full flex-shrink-0"
              style={{ background: cbOpen ? '#f87171' : '#4ade80' }}
            />
            <span className="hidden sm:block">{cbOpen ? 'OPEN' : 'CLOSED'}</span>
          </span>
        </div>
      </div>
    </aside>
  )
}
