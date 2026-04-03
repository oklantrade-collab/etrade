'use client'
import React from 'react'

interface FibBBPanelProps {
  symbol: string
  price: number
  levels: {
    basis: number
    upper_1: number; upper_2: number; upper_3: number; upper_4: number; upper_5: number; upper_6: number
    lower_1: number; lower_2: number; lower_3: number; lower_4: number; lower_5: number; lower_6: number
    zone: number
  }
}

export default function FibBBPanel({ symbol, price, levels }: FibBBPanelProps) {
  const getZoneLabel = (zone: number) => {
    if (zone >= 5) return { text: 'AGRESSIVE OVERBOUGHT', color: 'var(--accent-red)' }
    if (zone >= 1) return { text: 'BULLISH ZONE', color: 'var(--accent-green)' }
    if (zone === 0) return { text: 'NEUTRAL / BASIS', color: 'var(--text-muted)' }
    if (zone <= -5) return { text: 'AGRESSIVE OVERSOLD', color: 'var(--accent-blue)' }
    return { text: 'BEARISH ZONE', color: 'var(--accent-red)' }
  }

  const zoneInfo = getZoneLabel(levels.zone)

  const LevelRow = ({ label, value, isBasis = false, isTarget = false }: any) => (
    <div className={`flex justify-between items-center py-1.5 border-b border-[rgba(42,48,64,0.3)] ${isBasis ? 'text-purple-400 font-bold' : ''}`}>
      <span className="text-[0.75rem] uppercase tracking-wider text-slate-400">
        {label} {isTarget && '🎯'}
      </span>
      <span className="text-[0.9rem] font-mono">
        ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    </div>
  )

  return (
    <div className="card glass-effect overflow-hidden">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h3 className="text-lg font-bold tracking-tight">{symbol} Fibonacci BB</h3>
          <p className="text-xs text-slate-500 uppercase tracking-widest mt-1">15m Timeframe</p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold font-mono">${price.toLocaleString()}</div>
          <div className="text-[0.7rem] font-bold px-2 py-0.5 rounded-full inline-block mt-1" style={{ backgroundColor: `${zoneInfo.color}22`, color: zoneInfo.color, border: `1px solid ${zoneInfo.color}44` }}>
            {zoneInfo.text} (ZONE {levels.zone > 0 ? '+' : ''}{levels.zone})
          </div>
        </div>
      </div>

      <div className="space-y-0.5">
        <LevelRow label="🎯 TP AGR (upper_6)" value={levels.upper_6} />
        <LevelRow label="TP CONS (upper_5)" value={levels.upper_5} isTarget={true} />
        <div className="h-4" />
        <LevelRow label="Basis (VWMA)" value={levels.basis} isBasis={true} />
        <div className="h-4" />
        <LevelRow label="TP SHORT (lower_5)" value={levels.lower_5} />
        <LevelRow label="🎯 TP AGR (lower_6)" value={levels.lower_6} />
      </div>

      <div className="mt-8 pt-4 border-t border-slate-800">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <span className="text-[0.65rem] text-slate-500 uppercase block">Current Zone</span>
            <span className="text-sm font-bold text-slate-300">{levels.zone > 0 ? '+' : ''}{levels.zone}</span>
          </div>
          <div className="text-right">
            <span className="text-[0.65rem] text-slate-500 uppercase block">Distance to Basis</span>
            <span className="text-sm font-bold text-slate-300">
              {((price - levels.basis) / levels.basis * 100).toFixed(2)}%
            </span>
          </div>
        </div>
      </div>
      
      <style jsx>{`
        .glass-effect {
          background: rgba(26, 31, 46, 0.6);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
          border: 1px solid rgba(255, 255, 255, 0.05);
          box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }
      `}</style>
    </div>
  )
}
