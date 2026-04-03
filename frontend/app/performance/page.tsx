'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

interface PerformanceByRule {
  rule_code: string
  regime: string
  total_trades: number
  wins: number
  win_rate_pct: number
  avg_win_pct: number
  avg_loss_pct: number
  ev: number
  total_pnl_usd: number
  ultimo_trade: string
  paper_trades: number
  backtest_trades: number
}

interface PerformanceSummary {
  totalTrades: number
  winRateGlobal: number
  totalPnl: number
  avgEv: number
}

export default function PerformancePage() {
  const [performance, setPerformance] = useState<PerformanceByRule[]>([])
  const [recentTrades, setRecentTrades] = useState<any[]>([])
  const [summary, setSummary] = useState<PerformanceSummary>({
    totalTrades: 0, winRateGlobal: 0, totalPnl: 0, avgEv: 0
  })
  const [filters, setFilters] = useState({
    symbol: 'Todos',
    mode: 'Todos',
    period: '30 días'
  })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()

    const channel = supabase
      .channel('performance-realtime')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'paper_trades' }, () => loadData())
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [filters])

  async function loadData() {
    setLoading(true)
    try {
      // Build query params
      const params = new URLSearchParams()
      if (filters.symbol !== 'Todos') params.append('symbol', filters.symbol)
      if (filters.mode !== 'Todos') params.append('mode', filters.mode.toLowerCase())
      
      const daysMap: any = { '7 días': 7, '30 días': 30, 'Todo': 9999 }
      params.append('days', daysMap[filters.period] || 30)

      const res = await fetch(`/api/v1/performance/by-rule?${params.toString()}`)
      if (res.ok) {
        const data: PerformanceByRule[] = await res.json()
        // Sort by EV descending
        const sortedData = [...data].sort((a, b) => b.ev - a.ev)
        setPerformance(sortedData)

        // Calculate summary
        const totalTrades = sortedData.reduce((acc, curr) => acc + curr.total_trades, 0)
        const totalWins = sortedData.reduce((acc, curr) => acc + curr.wins, 0)
        const totalPnl = sortedData.reduce((acc, curr) => acc + curr.total_pnl_usd, 0)
        const avgEv = totalTrades > 0 ? sortedData.reduce((acc, curr) => acc + (curr.ev * curr.total_trades), 0) / totalTrades : 0

        setSummary({
          totalTrades,
          winRateGlobal: totalTrades > 0 ? (totalWins / totalTrades) * 100 : 0,
          totalPnl,
          avgEv
        })
      }

      // Load recent trades
      const recentRes = await supabase.from('paper_trades')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(20)
      
      if (recentRes.data) {
        setRecentTrades(recentRes.data)
      }

    } catch (err) {
      console.error('Performance load error:', err)
    } finally {
      setLoading(false)
    }
  }

  const getStatusIcon = (row: PerformanceByRule) => {
    if (row.total_trades < 10) return <span title="Menos de 10 trades" className="cursor-help">⏳</span>
    if (row.ev < 0) return <span title="EV negativo (candidata a desactivar)" className="cursor-help">⚠️</span>
    return <span title="EV positivo" className="cursor-help">✅</span>
  }

  // Group by regime for Section 4
  const regimeStats = performance.reduce((acc: any, curr) => {
    if (!acc[curr.regime]) {
      acc[curr.regime] = { trades: 0, wins: 0, evSum: 0, count: 0 }
    }
    acc[curr.regime].trades += curr.total_trades
    acc[curr.regime].wins += curr.wins
    acc[curr.regime].evSum += curr.ev * curr.total_trades
    acc[curr.regime].count += curr.total_trades
    return acc
  }, {})

  return (
    <div className="space-y-8 pb-10">
      <div className="page-header">
        <h1 className="text-3xl font-black italic tracking-tighter">Performance Dashboard</h1>
        <p className="text-xs text-slate-500 uppercase tracking-[0.2em] font-medium">Rule & Regime Analysis</p>
      </div>

      {/* SECCIÓN 1 — FILTROS */}
      <div className="flex flex-wrap gap-4 items-center bg-slate-900/40 p-4 rounded-xl border border-slate-800">
        <div className="space-y-1">
          <label className="text-[0.6rem] text-slate-500 uppercase font-bold px-1">Símbolo</label>
          <select 
            value={filters.symbol}
            onChange={(e) => setFilters({...filters, symbol: e.target.value})}
            className="bg-slate-900 border border-slate-700 rounded-lg text-xs px-3 py-2 text-white outline-none focus:border-blue-500 transition-colors"
          >
            {['Todos', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT'].map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-[0.6rem] text-slate-500 uppercase font-bold px-1">Modo</label>
          <select 
            value={filters.mode}
            onChange={(e) => setFilters({...filters, mode: e.target.value})}
            className="bg-slate-900 border border-slate-700 rounded-lg text-xs px-3 py-2 text-white outline-none focus:border-blue-500 transition-colors"
          >
            {['Todos', 'Paper', 'Backtest'].map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
        <div className="space-y-1">
          <label className="text-[0.6rem] text-slate-500 uppercase font-bold px-1">Período</label>
          <select 
            value={filters.period}
            onChange={(e) => setFilters({...filters, period: e.target.value})}
            className="bg-slate-900 border border-slate-700 rounded-lg text-xs px-3 py-2 text-white outline-none focus:border-blue-500 transition-colors"
          >
            {['7 días', '30 días', 'Todo'].map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      {/* SECCIÓN 2 — RESUMEN GENERAL */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="card glass-effect border-slate-800">
          <span className="text-[0.6rem] text-slate-500 uppercase font-black tracking-widest block mb-1">Total Trades</span>
          <span className="text-2xl font-black text-white">{summary.totalTrades}</span>
        </div>
        <div className="card glass-effect border-slate-800">
          <span className="text-[0.6rem] text-slate-500 uppercase font-black tracking-widest block mb-1">Win Rate Global</span>
          <span className="text-2xl font-black text-blue-500">{summary.winRateGlobal.toFixed(1)}%</span>
        </div>
        <div className="card glass-effect border-slate-800">
          <span className="text-[0.6rem] text-slate-500 uppercase font-black tracking-widest block mb-1">P&L Total</span>
          <span className={`text-2xl font-black ${summary.totalPnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
            {summary.totalPnl >= 0 ? '+' : ''}{summary.totalPnl.toFixed(2)} USDT
          </span>
        </div>
        <div className="card glass-effect border-slate-800">
          <span className="text-[0.6rem] text-slate-500 uppercase font-black tracking-widest block mb-1">EV Promedio</span>
          <span className={`text-2xl font-black ${summary.avgEv >= 0 ? 'text-blue-400' : 'text-amber-500'}`}>
            {summary.avgEv.toFixed(4)}
          </span>
        </div>
      </div>

      {/* SECCIÓN 3 — TABLA POR REGLA */}
      <div className="card glass-effect p-0 overflow-hidden border-slate-800">
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/30 flex justify-between items-center">
          <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Performance by Rule</h3>
          {performance.length === 0 && !loading && (
             <span className="text-xs text-amber-500 font-bold">Sin trades registrados aún. El sistema está acumulando datos en paper trading.</span>
          )}
        </div>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Regla</th>
                <th>Régimen</th>
                <th>Trades</th>
                <th>Win Rate</th>
                <th>EV</th>
                <th>P&L</th>
                <th>Paper/BT</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {performance.map((row, idx) => (
                <tr key={idx} className="hover:bg-white/5 transition-colors">
                  <td className="font-bold text-white">{row.rule_code}</td>
                  <td className="text-xs uppercase text-slate-400 font-medium">{row.regime.replace('_', ' ')}</td>
                  <td className="font-mono">{row.total_trades}</td>
                  <td className="font-bold text-blue-400">{row.win_rate_pct.toFixed(1)}%</td>
                  <td className={`font-mono font-bold ${row.ev >= 0 ? 'text-blue-400' : 'text-amber-500'}`}>
                    {row.ev.toFixed(4)}
                  </td>
                  <td className={`font-mono font-bold ${row.total_pnl_usd >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                    {row.total_pnl_usd.toFixed(2)}
                  </td>
                  <td className="text-[0.65rem] text-slate-500">
                    {row.paper_trades} / {row.backtest_trades}
                  </td>
                  <td className="text-lg">{getStatusIcon(row)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* SECCIÓN 4 — TABLA POR RÉGIMEN */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="card glass-effect p-0 overflow-hidden border-slate-800">
          <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/30">
            <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Performance by Regime</h3>
          </div>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Régimen</th>
                  <th>Trades</th>
                  <th>Win Rate</th>
                  <th>EV</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(regimeStats).map((reg, idx) => {
                  const s = regimeStats[reg]
                  const wr = s.trades > 0 ? (s.wins / s.trades) * 100 : 0
                  const ev = s.count > 0 ? s.evSum / s.count : 0
                  let emoji = '🟢'
                  if (reg.includes('alto')) emoji = '🔴'
                  if (reg.includes('medio')) emoji = '🟡'
                  
                  return (
                    <tr key={idx}>
                      <td className="font-bold text-white flex items-center gap-2">
                         <span>{emoji}</span> {reg.replace('_', ' ').toUpperCase()}
                      </td>
                      <td className="font-mono">{s.trades}</td>
                      <td className="font-bold text-blue-400">{wr.toFixed(1)}%</td>
                      <td className={`font-mono font-bold ${ev >= 0 ? 'text-blue-400' : 'text-amber-500'}`}>
                        {ev.toFixed(4)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
        
        <div className="card glass-effect border-slate-800 flex flex-col justify-center items-center text-center p-8">
           <div className="text-4xl mb-4">📈</div>
           <h3 className="text-lg font-black text-white italic tracking-tighter">Optimization Insight</h3>
           <p className="text-sm text-slate-400 mt-2">
             Las reglas con EV negativo y más de 10 trades deberían ser desactivadas o ajustadas en el Rule Engine para proteger el capital.
           </p>
        </div>
      </div>

      {/* SECCIÓN 5 — ÚLTIMOS TRADES */}
      <div className="card glass-effect p-0 overflow-hidden border-slate-800">
        <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/30">
          <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">Recent Trades (Last 20)</h3>
        </div>
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Fecha</th>
                <th>Símbolo</th>
                <th>Regla</th>
                <th>Side</th>
                <th>Entry</th>
                <th>Exit</th>
                <th>P&L</th>
                <th>Razón</th>
              </tr>
            </thead>
            <tbody>
              {recentTrades.map((t, idx) => (
                <tr key={idx}>
                  <td className="text-[0.65rem] text-slate-500 font-mono">
                    {new Date(t.created_at).toLocaleString()}
                  </td>
                  <td className="font-bold text-white">{t.symbol}</td>
                  <td className="text-xs font-mono text-slate-400">{t.rule_code}</td>
                  <td>
                    <span className={`px-2 py-0.5 rounded text-[0.6rem] font-black uppercase ${t.side === 'long' || t.side === 'BUY' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                      {t.side}
                    </span>
                  </td>
                  <td className="font-mono text-xs">${parseFloat(t.entry_price || t.avg_entry_price || 0).toFixed(4)}</td>
                  <td className="font-mono text-xs">${parseFloat(t.exit_price || 0).toFixed(4)}</td>
                  <td className={`font-mono font-bold ${parseFloat(t.total_pnl_usd || 0) >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                    {parseFloat(t.total_pnl_usd || 0) >= 0 ? '+' : ''}{parseFloat(t.total_pnl_usd || 0).toFixed(4)}
                  </td>
                  <td className="text-xs text-slate-400">{t.exit_reason || t.close_reason || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <style jsx>{`
        .glass-effect {
          background: rgba(26, 31, 46, 0.4);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .table-container {
          overflow-x: auto;
        }
        table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.8rem;
        }
        th {
          text-align: left;
          padding: 12px 24px;
          color: #64748b;
          text-transform: uppercase;
          font-weight: 800;
          letter-spacing: 0.1em;
          font-size: 0.65rem;
        }
        td {
          padding: 12px 24px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.02);
        }
      `}</style>
    </div>
  )
}
