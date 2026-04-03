// frontend/components/trading/BacktestPerformancePanel.tsx
'use client'
import { useState, useEffect } from 'react'
import { supabase } from '@/lib/supabase'

interface BacktestStats {
  rule_code: string
  trades: number
  wins: number
  win_rate: number
  avg_pnl_pct: number
  avg_adx: number
  expected_value: number
  regime: string
  ema20_phase: string
  close_reason: string
}

interface Summary {
  total_trades: number
  global_win_rate: number
  avg_ev: number
  best_rule: string
  profitable_rules: number
}

export default function BacktestPerformancePanel() {
  const [data, setData] = useState<BacktestStats[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [filterSymbol, setFilterSymbol] = useState('all')
  const [filterRegime, setFilterRegime] = useState('all')
  const [onlyProfitable, setOnlyProfitable] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sortConfig, setSortConfig] = useState<{ key: keyof BacktestStats, direction: 'asc' | 'desc' }>({ key: 'expected_value', direction: 'desc' })

  useEffect(() => {
    fetchPerformance()
  }, [filterSymbol, filterRegime])

  async function fetchPerformance() {
    setLoading(true)
    try {
      // Usamos el endpoint del backend.
      // Un URL relativo (/api/v1/...) es manejado por el proxy (next.config.ts)
      const response = await fetch(`/api/v1/backtests/performance?symbol=${filterSymbol}&regime=${filterRegime}`)
      const result = await response.json()
      
      if (result.rules) {
        setData(result.rules)
        setSummary(result.summary)
      }
    } catch (error) {
      console.error("Error fetching backtest performance:", error)
    } finally {
      setLoading(false)
    }
  }

  const sortedData = [...data].sort((a, b) => {
    const aValue = a[sortConfig.key]
    const bValue = b[sortConfig.key]
    if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1
    if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1
    return 0
  }).filter(item => onlyProfitable ? item.expected_value > 0 : true)

  const requestSort = (key: keyof BacktestStats) => {
    let direction: 'asc' | 'desc' = 'desc'
    if (sortConfig.key === key && sortConfig.direction === 'desc') {
      direction = 'asc'
    }
    setSortConfig({ key, direction })
  }

  const getRegimeBadge = (regime: string) => {
    const styles: any = {
      'alto_riesgo': 'bg-rose-500/10 text-rose-500 border-rose-500/20',
      'riesgo_medio': 'bg-amber-500/10 text-amber-500 border-amber-500/20',
      'bajo_riesgo': 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
      'all': 'bg-slate-500/10 text-slate-500 border-slate-500/20'
    }
    return <span className={`px-2 py-0.5 rounded border text-[9px] font-black uppercase ${styles[regime] || styles.all}`}>{regime.replace('_', ' ')}</span>
  }

  return (
    <div className="space-y-6">
      {/* Resumen Superior */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="card glass-effect p-4 border-blue-500/10">
          <p className="text-[10px] text-slate-500 uppercase font-black tracking-widest">Total Trades</p>
          <h4 className="text-2xl font-black italic tracking-tighter text-blue-400">{summary?.total_trades || 0}</h4>
        </div>
        <div className="card glass-effect p-4 border-emerald-500/10">
          <p className="text-[10px] text-slate-500 uppercase font-black tracking-widest">Global Win Rate</p>
          <h4 className="text-2xl font-black italic tracking-tighter text-emerald-400">{(summary?.global_win_rate || 0).toFixed(1)}%</h4>
        </div>
        <div className="card glass-effect p-4 border-purple-500/10">
          <p className="text-[10px] text-slate-500 uppercase font-black tracking-widest">EV Promedio</p>
          <h4 className="text-2xl font-black italic tracking-tighter text-purple-400">{(summary?.avg_ev || 0).toFixed(3)}</h4>
        </div>
        <div className="card glass-effect p-4 border-amber-500/10 text-right">
          <p className="text-[10px] text-slate-500 uppercase font-black tracking-widest">Reglas Rentables</p>
          <h4 className="text-2xl font-black italic tracking-tighter text-amber-400">{summary?.profitable_rules || 0} / 13</h4>
        </div>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap gap-4 items-center bg-slate-900/30 p-3 rounded-xl border border-white/5">
        <select 
          value={filterSymbol} 
          onChange={(e) => setFilterSymbol(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs text-slate-300 outline-none focus:border-blue-500"
        >
          <option value="all">TODOS LOS SÍMBOLOS</option>
          <option value="BTCUSDT">BTC/USDT</option>
          <option value="ETHUSDT">ETH/USDT</option>
          <option value="SOLUSDT">SOL/USDT</option>
          <option value="ADAUSDT">ADA/USDT</option>
        </select>

        <select 
          value={filterRegime} 
          onChange={(e) => setFilterRegime(e.target.value)}
          className="bg-slate-950 border border-slate-800 rounded px-3 py-1.5 text-xs text-slate-300 outline-none focus:border-blue-500"
        >
          <option value="all">TODOS LOS REGÍMENES</option>
          <option value="bajo_riesgo">BAJO RIESGO</option>
          <option value="riesgo_medio">RIESGO MEDIO</option>
          <option value="alto_riesgo">ALTO RIESGO</option>
        </select>

        <label className="flex items-center gap-2 cursor-pointer group">
          <input 
            type="checkbox" 
            checked={onlyProfitable} 
            onChange={(e) => setOnlyProfitable(e.target.checked)}
            className="w-4 h-4 rounded border-slate-800 bg-slate-950 text-blue-500"
          />
          <span className="text-[10px] font-bold uppercase text-slate-500 group-hover:text-slate-300">SOLO RENTABLES (EV &gt; 0)</span>
        </label>
      </div>

      {/* Tabla de Performance */}
      <div className="card glass-effect overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="bg-slate-900/50 border-b border-white/5 text-slate-500 font-black uppercase tracking-tighter">
                <th className="p-4 cursor-pointer hover:text-white" onClick={() => requestSort('rule_code')}>Regla</th>
                <th className="p-4 cursor-pointer hover:text-white" onClick={() => requestSort('trades')}>Trades</th>
                <th className="p-4 cursor-pointer hover:text-white" onClick={() => requestSort('win_rate')}>Win Rate</th>
                <th className="p-4 cursor-pointer hover:text-white text-right" onClick={() => requestSort('expected_value')}>EV</th>
                <th className="p-4 cursor-pointer hover:text-white text-right" onClick={() => requestSort('avg_pnl_pct')}>Avg PnL</th>
                <th className="p-4 cursor-pointer hover:text-white" onClick={() => requestSort('avg_adx')}>ADX Prom</th>
                <th className="p-4">Régimen</th>
                <th className="p-4">Fase EMA</th>
                <th className="p-4">Cierre</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading ? (
                <tr>
                  <td colSpan={9} className="p-20 text-center text-slate-500 italic">Analizando histórico de backtesting...</td>
                </tr>
              ) : sortedData.map((item, idx) => (
                <tr key={`${item.rule_code}-${idx}`} className="group hover:bg-white/[0.02] transition-colors">
                  <td className="p-4">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-black italic tracking-tighter border ${item.rule_code.startsWith('A') ? 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20' : 'bg-rose-500/10 text-rose-500 border-rose-500/20'}`}>
                      {item.rule_code}
                    </span>
                  </td>
                  <td className="p-4 font-bold text-slate-400">{item.trades}</td>
                  <td className="p-4">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden max-w-[60px]">
                        <div 
                          className={`h-full rounded-full ${item.win_rate >= 50 ? 'bg-emerald-500' : 'bg-rose-500'}`}
                          style={{ width: `${item.win_rate}%` }}
                        />
                      </div>
                      <span className="font-bold text-slate-300">{(item.win_rate).toFixed(1)}%</span>
                    </div>
                  </td>
                  <td className="p-4 text-right">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-black italic border ${item.expected_value > 0 ? 'text-emerald-400 border-emerald-400/20 bg-emerald-400/5' : 'text-rose-400 border-rose-400/20 bg-rose-400/5'}`}>
                      {(item.expected_value).toFixed(3)}
                    </span>
                  </td>
                  <td className={`p-4 text-right font-bold ${item.avg_pnl_pct >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                    {(item.avg_pnl_pct).toFixed(2)}%
                  </td>
                  <td className="p-4 text-slate-400">{(item.avg_adx).toFixed(1)}</td>
                  <td className="p-4">
                    {getRegimeBadge(item.regime)}
                  </td>
                  <td className="p-4 text-[10px] uppercase font-bold text-slate-600 truncate max-w-[80px]">
                    {item.ema20_phase}
                  </td>
                  <td className="p-4 text-[9px] font-black uppercase tracking-tighter text-slate-500">
                    {item.close_reason.replace('_', ' ')}
                  </td>
                </tr>
              ))}
              {sortedData.length === 0 && !loading && (
                <tr>
                  <td colSpan={9} className="p-20 text-center text-slate-500 italic">No se encontraron datos para estos filtros.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
