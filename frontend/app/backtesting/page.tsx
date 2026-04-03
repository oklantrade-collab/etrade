'use client'
import { useEffect, useState } from 'react'
import BacktestPerformancePanel from '@/components/trading/BacktestPerformancePanel'
import { supabase } from '@/lib/supabase'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'

interface RunData {
  id: string
  symbol: string
  start_date: string
  end_date: string
  initial_capital: number
  final_capital: number
  total_return_pct: number
  win_rate: number
  profit_factor: number
  sharpe_ratio: number
  max_drawdown_pct: number
  total_trades: number
  status: string
  created_at: string
}

export default function BacktestingPage() {
  const [runs, setRuns] = useState<RunData[]>([])
  const [showModal, setShowModal] = useState(false)
  const [expandedRun, setExpandedRun] = useState<any>(null)
  
  // Form state
  const [symbols, setSymbols] = useState<string[]>([])
  const [symbol, setSymbol] = useState('')
  const [startDate, setStartDate] = useState('2025-11-01')
  const [endDate, setEndDate] = useState('2026-03-14')
  const [initialCapital, setInitialCapital] = useState(10000)
  
  // Advanced Form State
  const [showAdvanced, setShowAdvanced] = useState(false)
  const [spikeMultiplier, setSpikeMultiplier] = useState(2.5)
  const [mtfThreshold, setMtfThreshold] = useState(0.65)
  const [slMultiplier, setSlMultiplier] = useState(2.0)
  const [rrRatio, setRrRatio] = useState(2.5)
  const [riskPct, setRiskPct] = useState(1.0)

  useEffect(() => {
    loadRuns()
    loadSymbols()
    
    // Polling cada 5 seg
    const interval = setInterval(() => {
      loadRuns(true)
    }, 5000)
    
    return () => clearInterval(interval)
  }, [])

  async function loadSymbols() {
    try {
      // 1. Obtener símbolos permitidos desde la configuración del sistema
      const { data: configData } = await supabase
        .from('system_config')
        .select('value')
        .eq('key', 'allowed_symbols')
        .single()
      
      let allowed: string[] = []
      if (configData?.value) {
        const val = configData.value
        // Puede venir como string "BTCUSDT,ETHUSDT" o como array ["BTCUSDT", ...]
        const rawList = typeof val === 'string' ? val.split(',') : (Array.isArray(val) ? val : [])
        allowed = rawList.map((s: string) => {
          const clean = s.trim().toUpperCase()
          if (clean.endsWith('USDT')) {
            return clean.replace('USDT', '/USDT')
          }
          return clean
        })
      }

      // 2. Si no hay configuración, usamos un fallback básico
      if (allowed.length === 0) {
        allowed = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ADA/USDT']
      }
      
      setSymbols(allowed)
      
      // 3. Seleccionamos BTC/USDT por defecto si está en la lista
      if (allowed.includes('BTC/USDT')) {
        setSymbol('BTC/USDT')
      } else {
        setSymbol(allowed[0])
      }
      
    } catch (e) {
      console.error("Error loading symbols from config:", e)
      const defaults = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'ADA/USDT']
      setSymbols(defaults)
      setSymbol('BTC/USDT')
    }
  }

  async function loadRuns(silent = false) {
    try {
      const res = await fetch('/api/v1/backtests')
      if (res.ok) {
        const data = await res.json()
        setRuns(data)
      }
    } catch (err) {
      // API fallback just in case:
      const { data } = await supabase.from('backtest_runs')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(20)
      if (data) setRuns(data)
    }
  }

  async function handleRunBacktest() {
    const payload = {
      symbol: symbol,
      start_date: startDate,
      end_date: endDate,
      initial_capital: initialCapital,
      spike_multiplier: spikeMultiplier,
      mtf_signal_threshold: mtfThreshold,
      sl_multiplier: slMultiplier,
      rr_ratio: rrRatio,
      risk_pct: riskPct / 100.0,
    }
    
    try {
      const res = await fetch('/api/v1/backtests/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      
      if (res.ok) {
        setShowModal(false)
        loadRuns()
      } else {
        const err = await res.json()
        alert(`Error: ${err.detail || 'Could not start backtest'}`)
      }
    } catch (e) {
      console.error(e)
      alert("Error de conexión con el backend. Verifica que el servicio de API esté activo.")
    }
  }

  async function expandRow(runId: string) {
    if (expandedRun?.id === runId) {
      setExpandedRun(null)
      return
    }
    
    try {
      const res = await fetch(`/api/v1/backtests/${runId}`)
      if (res.ok) {
        const data = await res.json()
        setExpandedRun(data)
      } else {
        // Fallback to Supabase if Nextjs rewrite fails
        const { data } = await supabase.from('backtest_runs').select('*').eq('id', runId).single()
        if (data) setExpandedRun(data)
      }
    } catch (e) {
      console.error(e)
    }
  }

  async function deleteRun(e: React.MouseEvent, runId: string) {
    e.stopPropagation()
    if (!confirm('¿Eliminar este registro de backtest?')) return
    
    try {
      await fetch(`/api/v1/backtests/${runId}`, { method: 'DELETE' })
      loadRuns()
      if (expandedRun?.id === runId) setExpandedRun(null)
    } catch (e) {
      console.error(e)
    }
  }

  const fmtColor = (val: number, type: 'pnl' | 'wr' | 'pf' | 'sharpe' | 'dd') => {
    if (type === 'pnl') return val >= 0 ? '#22C55E' : '#EF4444'
    if (type === 'wr') return val >= 50 ? '#22C55E' : 'inherit'
    if (type === 'pf') return val >= 1.5 ? '#22C55E' : val < 1.0 ? '#EF4444' : 'inherit'
    if (type === 'sharpe') return val >= 1.0 ? '#22C55E' : 'inherit'
    if (type === 'dd') return val < 15 ? '#22C55E' : val <= 25 ? '#EAB308' : '#EF4444'
    return 'inherit'
  }

  return (
    <div>
      <div className="page-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <h1>Backtesting Engine</h1>
          <p>Strategy validation with historical market data</p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          New Run
        </button>
      </div>

      <div className="card">
        <div className="card-header">
           <span className="card-title">Backtest History</span>
        </div>
        
        {runs.length > 0 ? (
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Period</th>
                  <th>Capital</th>
                  <th>Return</th>
                  <th>Win Rate</th>
                  <th>Profit Factor</th>
                  <th>Sharpe</th>
                  <th>Max DD</th>
                  <th>Trades</th>
                  <th>Acciones</th>
                </tr>
              </thead>
              <tbody>
                {runs.map(r => (
                  <tr key={r.id} onClick={() => expandRow(r.id)} style={{ cursor: 'pointer', background: expandedRun?.id === r.id ? 'var(--bg-card)' : 'transparent' }}>
                    <td style={{ fontWeight: 600 }}>
                      {r.status === 'running' && <span>⏳ </span>}
                      {r.status === 'error' && <span title={r.status}>❌ </span>}
                      {r.symbol}
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{r.start_date} to {r.end_date}</td>
                    <td>${Number(r.initial_capital).toFixed(0)}</td>
                    {r.status === 'completed' ? (
                      <>
                        <td style={{ color: fmtColor(r.total_return_pct, 'pnl'), fontWeight: 600 }}>
                          {r.total_return_pct >= 0 ? '+' : ''}{Number(r.total_return_pct).toFixed(2)}%
                        </td>
                        <td style={{ color: fmtColor(r.win_rate, 'wr') }}>{Number(r.win_rate).toFixed(1)}%</td>
                        <td style={{ color: fmtColor(r.profit_factor, 'pf') }}>{Number(r.profit_factor).toFixed(2)}</td>
                        <td style={{ color: fmtColor(r.sharpe_ratio, 'sharpe') }}>{Number(r.sharpe_ratio).toFixed(2)}</td>
                        <td style={{ color: fmtColor(r.max_drawdown_pct, 'dd') }}>-{Number(r.max_drawdown_pct).toFixed(2)}%</td>
                        <td>{r.total_trades}</td>
                      </>
                    ) : (
                       <td colSpan={6} style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
                         {r.status === 'running' ? 'Calculating metrics...' : 'Failed'}
                       </td>
                    )}
                    <td onClick={(e) => e.stopPropagation()}>
                      <button 
                        onClick={(e) => deleteRun(e, r.id)}
                        style={{ background: 'transparent', border: 'none', color: 'var(--accent-red)', cursor: 'pointer', fontSize: '1.2rem' }}
                        title="Eliminar"
                      >
                        🗑️
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
             No backtests have been run yet.
          </div>
        )}
      </div>

      {expandedRun && expandedRun.status === 'completed' && (
        <div className="card" style={{ marginTop: '24px', borderTop: '4px solid var(--accent-blue)' }}>
          <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span className="card-title">Results: {expandedRun.symbol} ({expandedRun.start_date} - {expandedRun.end_date})</span>
            <button className="btn" onClick={() => setExpandedRun(null)} style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)' }}>✕</button>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(0, 1fr)', gap: '24px', marginTop: '16px' }}>
            {/* Equity Curve */}
            <div>
              <h4 style={{ marginBottom: '16px', color: 'var(--text-secondary)' }}>Equity Curve</h4>
              <div style={{ width: '100%', height: 280 }}>
                {expandedRun.equity_curve ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={expandedRun.equity_curve}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1E293B"/>
                      <XAxis dataKey="timestamp"
                             tickFormatter={t => new Date(t).toLocaleDateString()}
                             stroke="#6B7280" tick={{ fontSize: 11 }}/>
                      <YAxis domain={['auto', 'auto']}
                             tickFormatter={v => `$${v.toLocaleString()}`}
                             stroke="#6B7280" tick={{ fontSize: 11 }}/>
                      <Tooltip
                             formatter={(v: any) => [`$${Number(v).toLocaleString()}`, 'Capital']}
                             labelFormatter={(l: any) => new Date(l).toLocaleString()}
                             contentStyle={{ background: '#1E293B', border: 'none', color: '#F8FAFC' }}/>
                      <ReferenceLine y={expandedRun.initial_capital} stroke="#6B7280" strokeDasharray="5 5"/>
                      <Line type="monotone" dataKey="equity"
                             stroke={expandedRun.final_capital >= expandedRun.initial_capital ? '#22C55E' : '#EF4444'} 
                             dot={false} strokeWidth={2}/>
                    </LineChart>
                  </ResponsiveContainer>
                ) : (
                  <div style={{ display: 'flex', height: '100%', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
                    No equity curve data available.
                  </div>
                )}
              </div>
            </div>
            
            {/* Metrics Grid */}
            <div>
              <h4 style={{ marginBottom: '16px', color: 'var(--text-secondary)' }}>Key Metrics</h4>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                <div style={{ background: 'var(--bg-body)', padding: '16px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Win Rate</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 600, color: fmtColor(expandedRun.win_rate, 'wr') }}>
                    {Number(expandedRun.win_rate).toFixed(1)}%
                  </div>
                </div>
                <div style={{ background: 'var(--bg-body)', padding: '16px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Profit Factor</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 600, color: fmtColor(expandedRun.profit_factor, 'pf') }}>
                    {Number(expandedRun.profit_factor).toFixed(2)}
                  </div>
                </div>
                <div style={{ background: 'var(--bg-body)', padding: '16px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Sharpe Ratio</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 600, color: fmtColor(expandedRun.sharpe_ratio, 'sharpe') }}>
                    {Number(expandedRun.sharpe_ratio).toFixed(2)}
                  </div>
                </div>
                <div style={{ background: 'var(--bg-body)', padding: '16px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Max Drawdown</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 600, color: fmtColor(expandedRun.max_drawdown_pct, 'dd') }}>
                    -{Number(expandedRun.max_drawdown_pct).toFixed(1)}%
                  </div>
                </div>
                <div style={{ background: 'var(--bg-body)', padding: '16px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Total Trades</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
                    {expandedRun.total_trades}
                  </div>
                </div>
                <div style={{ background: 'var(--bg-body)', padding: '16px', borderRadius: '8px' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '4px' }}>Avg Duration</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>
                    {Number(expandedRun.avg_trade_duration_hrs).toFixed(1)}h
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* New Run Modal */}
      {showModal && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(4px)' }}>
          <div className="card" style={{ width: 500, maxWidth: '90%' }}>
            <h2 style={{ marginTop: 0, marginBottom: 24 }}>New Backtest Run</h2>
            
            <div style={{ display: 'grid', gap: 16 }}>
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontSize: '0.875rem' }}>Symbol</label>
                <select value={symbol} onChange={e => setSymbol(e.target.value)} style={{ width: '100%', padding: '8px 12px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 6, color: '#F8FAFC', outline: 'none' }}>
                  {!symbol && <option value="" style={{ background: '#1E293B', color: '#F8FAFC' }}>-- Seleccionar --</option>}
                  {symbols.map(s => (
                    <option key={s} value={s} style={{ background: '#1E293B', color: '#F8FAFC' }}>
                      {s}
                    </option>
                  ))}
                </select>
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontSize: '0.875rem' }}>Start Date</label>
                  <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} style={{ width: '100%', padding: '8px 12px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 6, color: 'white' }} />
                </div>
                <div>
                  <label style={{ display: 'block', marginBottom: 6, fontSize: '0.875rem' }}>End Date</label>
                  <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} style={{ width: '100%', padding: '8px 12px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 6, color: 'white' }} />
                </div>
              </div>
              
              <div>
                <label style={{ display: 'block', marginBottom: 6, fontSize: '0.875rem' }}>Initial Capital ($)</label>
                <input type="number" value={initialCapital} onChange={e => setInitialCapital(Number(e.target.value))} style={{ width: '100%', padding: '8px 12px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 6, color: 'white' }} />
              </div>
              
              <div className="advanced-options" style={{ marginTop: 8 }}>
                <div onClick={() => setShowAdvanced(!showAdvanced)} style={{ cursor: 'pointer', color: 'var(--accent-blue)', display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.875rem' }}>
                  <span>{showAdvanced ? '▼' : '▶'}</span>
                  <span>Parámetros Avanzados</span>
                </div>
                
                {showAdvanced && (
                  <div style={{ marginTop: 16, padding: 16, border: '1px solid var(--border-color)', borderRadius: 6, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, background: 'rgba(255,255,255,0.02)' }}>
                    <div>
                      <label style={{ display: 'block', marginBottom: 6, fontSize: '0.75rem', color: 'var(--text-muted)' }}>Spike Multiplier</label>
                      <input type="number" step="0.1" value={spikeMultiplier} onChange={e => setSpikeMultiplier(Number(e.target.value))} style={{ width: '100%', padding: '6px 8px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 4, color: 'white', fontSize: '0.875rem' }} />
                    </div>
                    <div>
                      <label style={{ display: 'block', marginBottom: 6, fontSize: '0.75rem', color: 'var(--text-muted)' }}>MTF Threshold</label>
                      <input type="number" step="0.05" value={mtfThreshold} onChange={e => setMtfThreshold(Number(e.target.value))} style={{ width: '100%', padding: '6px 8px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 4, color: 'white', fontSize: '0.875rem' }} />
                    </div>
                    <div>
                      <label style={{ display: 'block', marginBottom: 6, fontSize: '0.75rem', color: 'var(--text-muted)' }}>SL (ATR X)</label>
                      <input type="number" step="0.1" value={slMultiplier} onChange={e => setSlMultiplier(Number(e.target.value))} style={{ width: '100%', padding: '6px 8px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 4, color: 'white', fontSize: '0.875rem' }} />
                    </div>
                    <div>
                      <label style={{ display: 'block', marginBottom: 6, fontSize: '0.75rem', color: 'var(--text-muted)' }}>RR Ratio</label>
                      <input type="number" step="0.1" value={rrRatio} onChange={e => setRrRatio(Number(e.target.value))} style={{ width: '100%', padding: '6px 8px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 4, color: 'white', fontSize: '0.875rem' }} />
                    </div>
                    <div style={{ gridColumn: '1 / -1' }}>
                      <label style={{ display: 'block', marginBottom: 6, fontSize: '0.75rem', color: 'var(--text-muted)' }}>Risk Per Trade (%)</label>
                      <input type="number" step="0.1" value={riskPct} onChange={e => setRiskPct(Number(e.target.value))} style={{ width: '100%', padding: '6px 8px', background: 'var(--bg-body)', border: '1px solid var(--border-color)', borderRadius: 4, color: 'white', fontSize: '0.875rem' }} />
                    </div>
                  </div>
                )}
              </div>
            </div>
            
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 32 }}>
              <button className="btn" onClick={() => setShowModal(false)} style={{ background: 'transparent', border: '1px solid var(--border-color)' }}>Cancelar</button>
              <button className="btn btn-primary" onClick={handleRunBacktest}>▶ Ejecutar Backtest</button>
            </div>
          </div>
        </div>
      )}
      {/* Panel de Performance por Regla (Sprint 2 - Paso 3) */}
      <div style={{ marginTop: '40px', marginBottom: '80px' }}>
        <div className="section-header">
          <h2 className="text-xl font-black italic tracking-tighter">Rule Performance Matrix</h2>
          <p className="text-slate-500 text-xs">Análisis estadístico de cada regla de entrada en el histórico de backtesting</p>
        </div>
        <div style={{ marginTop: '20px' }}>
          <BacktestPerformancePanel />
        </div>
      </div>
    </div>
  )
}
