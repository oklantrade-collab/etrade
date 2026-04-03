'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import Link from 'next/link'
import TradeMarkerChart, { TradeEvent } from '@/components/TradeMarkerChart'
import RuleDiagnosticPanel from '@/components/RuleDiagnosticPanel'

interface SymbolData {
  price: number
  zone: number
  basis: number
  upper_5: number
  upper_6: number
  lower_5: number
  lower_6: number
  mtf_score: number
  ema20_phase: string
  adx: number
  dist_basis_pct: number
  spike?: {
    detected: boolean
    ratio: number
    direction: string
  }
  regime: string
  ai_sentiment: string
  card_status?: string
  sar_4h?: number
  sar_trend_4h?: number
  sar_phase?: 'long' | 'short' | 'neutral'
  sar_phase_changed_at?: string
  position?: {
    side: 'long' | 'short'
    trades_count: number
    avg_entry: number
    sl_price: number
    tp_partial: number
    tp_full: number
    unrealized_pnl_usd: number
    unrealized_pnl_pct: number
    breakeven_hit: boolean
    bars_held: number
    max_bars: number
    rule_code: string | null
    regime_entry?: string
  }
  last_signal?: {
    rule_code: string
    direction: string
    score: number
    status: string
    blocked_reason?: string
  }
  volume_rel?: number
  cur_vol?: number
  vol_ema?: number
  dynamic_tp?: {
    next_target: {
      target_name: string
      target_price: number
      target_zone: number
    }
    after_next_target: {
      target_name: string
      target_price: number
      target_zone: number
    }
    decision: {
      action: 'hold' | 'partial_close' | 'full_close'
      pct?: number
      reason: string
    }
  }
}

interface DashboardData {
  daily: {
    total_pnl: number
    daily_pnl: number
    live_pnl: number
    total_trades: number
    win_rate: number
    open_positions: number
  }
  symbols: Record<string, SymbolData>
  focus_symbol: string
  recent_signals: any[]
  market_feed: any[]
  config: {
    capital_per_symbol: number
    leverage: number
  }
}

const TIMEFRAMES = [
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '30m', value: '30m' },
  { label: '4h', value: '4h' },
  { label: '1d', value: '1d' }
]

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null)
  const [diagnosticSymbol, setDiagnosticSymbol] = useState<string | null>(null)
  const [selectedTf, setSelectedTf] = useState('15m')
  const [candles, setCandles] = useState<any[]>([])
  const [trades, setTrades] = useState<TradeEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [chartLoading, setChartLoading] = useState(false)
  const [mode, setMode] = useState<string | null>(null)

  useEffect(() => {
    setMode(localStorage.getItem('etrade_mode') || 'paper')
    loadData()

    const channel = supabase
      .channel('dashboard-realtime-v4')
      .on('postgres_changes', { event: '*', schema: 'public', table: 'cron_cycles' }, () => loadData())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'trading_signals' }, () => loadData())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'positions' }, () => loadData())
      .on('postgres_changes', { event: '*', schema: 'public', table: 'market_regime' }, () => loadData())
      .on('postgres_changes', { 
        event: 'INSERT', 
        schema: 'public', 
        table: 'market_snapshot' 
      }, (payload) => updateSymbolData(payload.new.symbol, payload.new))
      .on('postgres_changes', { 
        event: 'UPDATE', 
        schema: 'public', 
        table: 'market_snapshot' 
      }, (payload) => updateSymbolData(payload.new.symbol, payload.new))
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [])

  useEffect(() => {
    if (selectedSymbol) {
      loadChartData(selectedSymbol, selectedTf)
      
      // MEJORA: Refrescar velas cada 5 minutos
      const interval = setInterval(() => {
        loadChartData(selectedSymbol, selectedTf)
      }, 5 * 60 * 1000)
      
      return () => clearInterval(interval)
    }
  }, [selectedSymbol, selectedTf])

  const updateSymbolData = (symbol: string, newData: any) => {
    setData(prev => {
      if (!prev) return prev;
      const symbols = { ...prev.symbols };
      const config = prev.config || { capital_per_symbol: 18, leverage: 5 };
      
      if (symbols[symbol]) {
        const info = symbols[symbol];
        const newPrice = parseFloat(newData.price || info.price);
        
        let newPos = info.position ? { ...info.position } : undefined;
        if (newPos && newPos.avg_entry > 0) {
           const entry = newPos.avg_entry;
           const side = newPos.side.toLowerCase();
           const pct = side === 'long' 
             ? (newPrice - entry) / entry * 100
             : (entry - newPrice) / entry * 100;
           
           const capitalUsed = config.capital_per_symbol * config.leverage;
           
           newPos.unrealized_pnl_pct = pct;
           newPos.unrealized_pnl_usd = parseFloat((capitalUsed * pct / 100).toFixed(2));
        }

        symbols[symbol] = { 
          ...info, 
          ...newData,
          price: newPrice,
          zone: parseInt(newData.fibonacci_zone ?? info.zone),
          position: newPos
        };
      }
      return { ...prev, symbols };
    });
  };

  async function loadData() {
    try {
      const res = await fetch('/api/v1/dashboard/summary')
      if (res.ok) {
        const json: DashboardData = await res.json()
        
        // Recalcular P&L inicial usando la lógica solicitada
        const config = json.config || { capital_per_symbol: 18, leverage: 5 }
        Object.keys(json.symbols).forEach(sym => {
           const info = json.symbols[sym]
           if (info.position && info.position.avg_entry > 0) {
              const entry = info.position.avg_entry
              const curPrice = info.price
              const side = info.position.side.toLowerCase()
              const pct = side === 'long' 
                ? (curPrice - entry) / entry * 100
                : (entry - curPrice) / entry * 100
              
              const capUsed = config.capital_per_symbol * config.leverage
              info.position.unrealized_pnl_pct = pct
              info.position.unrealized_pnl_usd = parseFloat((capUsed * pct / 100).toFixed(2))
           }
        })

        setData(json)
        if (!selectedSymbol) {
          setSelectedSymbol(json.focus_symbol)
        }
      }
    } catch (err) {
      console.error('Dashboard load error:', err)
    } finally {
      setLoading(false)
    }
  }

  async function loadChartData(symbol: string, tf: string) {
    setChartLoading(true)
    try {
      const [cRes, tRes] = await Promise.all([
        fetch(`/api/v1/market/candles/${symbol}?timeframe=${tf}&limit=200`),
        fetch(`/api/v1/market/trade-events/${symbol}?days=7`)
      ])
      if (cRes.ok) {
        const cJson = await cRes.json()
        setCandles(cJson.candles || [])
      }
      if (tRes.ok) {
        const tJson = await tRes.json()
        setTrades(tJson || [])
      }
    } catch (err) {
      console.error('Chart data load error:', err)
    } finally {
      setChartLoading(false)
    }
  }

  const currentFocus = selectedSymbol && data?.symbols[selectedSymbol] ? data.symbols[selectedSymbol] : null

  if (loading || !data) return <div className="p-10 text-slate-500 italic">Cargando Command Center...</div>

  return (
    <div className="space-y-8 pb-20">
      {/* SECCIÓN 1 — Header con breadcrumb */}
      <div className="flex justify-between items-center">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-[0.65rem] font-black text-slate-500 uppercase tracking-widest">
            <Link href="/portfolio" className="hover:text-blue-400">Portfolio</Link>
            <span>/</span>
            <span className="text-slate-300">Crypto</span>
          </div>
          <h1 className="text-3xl font-black italic tracking-tighter">Command Center</h1>
        </div>
        
        <div className="flex items-center gap-6">
          <Link 
            href="/strategies" 
            className="flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 px-4 py-2 rounded-xl border opacity-80 hover:opacity-100 hover:bg-indigo-500/20 transition-all shadow-[0_0_15px_rgba(99,102,241,0.05)]"
          >
             <span className="text-xl">🧠</span>
             <span className="text-xs font-black text-indigo-400 uppercase tracking-widest">Engine v1.0</span>
          </Link>
          <div className="flex items-center gap-2 bg-blue-500/10 border border-blue-500/20 px-4 py-2 rounded-xl">
             <span className="text-xl">📄</span>
             <span className="text-xs font-black text-blue-400 uppercase tracking-widest">{mode?.toUpperCase()} Trading</span>
          </div>
          <div className="w-px h-10 bg-slate-800" />
          <div className="text-right">
             <span className="text-[0.6rem] text-slate-500 uppercase font-black block leading-none mb-1">Risk Regime</span>
             <span className="text-sm font-black text-amber-500 uppercase italic">🟡 Riesgo Medio</span>
          </div>
          <div className="text-right">
             <span className="text-[0.6rem] text-slate-500 uppercase font-black block leading-none mb-1">Cycle Status</span>
             <div className="flex items-center justify-end gap-2 text-sm font-black text-emerald-500 italic">
               <div className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" />
               Active
             </div>
          </div>
          <div className="text-right border-l border-slate-800 pl-6">
             <span className="text-[0.6rem] text-slate-500 uppercase font-black block leading-none mb-1">Local Time (LIMA)</span>
             <span className="text-sm font-black text-white italic">
               {new Date().toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
             </span>
          </div>
        </div>
      </div>

      {/* SECCIÓN 2 — Métricas del día */}
      <div className="grid grid-cols-4 gap-6">
        <MetricCard label="P&L HOY" value={`$${data.daily.daily_pnl.toFixed(2)}`} color={data.daily.daily_pnl >=0 ? 'text-emerald-500' : 'text-rose-500'} />
        <MetricCard label="WIN RATE" value={`${data.daily.win_rate}%`} color="text-indigo-400" />
        <MetricCard label="POSICIONES" value={`${data.daily.open_positions}`} color="text-blue-400" />
        <MetricCard label="RISK STATUS" value="MEDIUM" color="text-amber-500" />
      </div>

      {/* SECCIÓN 2.5 — Resumen Consolidado de Posiciones Abiertas */}
      {(() => {
        const symbolsWithPos = Object.entries(data.symbols)
          .filter(([_, info]) => info.position)
          .map(([sym, info]) => ({ symbol: sym, ...info }));
        
        if (symbolsWithPos.length === 0) return null;

        const totalPnL = symbolsWithPos.reduce((acc, s) => acc + (s.position?.unrealized_pnl_usd || 0), 0);
        const totalCapital = symbolsWithPos.reduce((acc, s) => {
          const capPerSym = data.config?.capital_per_symbol || 18;
          const leverage = data.config?.leverage || 5;
          return acc + (capPerSym * leverage);
        }, 0);
        const avgPnLPct = totalCapital > 0 ? (totalPnL / totalCapital * 100) : 0;
        const capitalInUsePct = Math.min((totalCapital / ((data.config?.capital_per_symbol || 18) * 8 * (data.config?.leverage || 5))) * 100, 100);

        return (
          <div className="card glass-effect border-slate-800/50 p-6 shadow-xl relative overflow-hidden">
            <div className="absolute top-0 left-0 w-1 h-full bg-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.5)]" />
            <div className="flex flex-col md:flex-row justify-between items-center gap-6">
              <div className="flex-1 space-y-4 w-full">
                <div className="flex justify-between items-center">
                   <h3 className="text-[0.6rem] font-black text-slate-500 uppercase tracking-[0.3em]">Posiciones Abiertas — P&L No Realizado</h3>
                   <span className="text-[0.6rem] font-bold text-slate-400">Capital en Uso: ${totalCapital.toFixed(0)}</span>
                </div>
                <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                  {symbolsWithPos.map(s => (
                    <div key={s.symbol} className="flex justify-between items-center bg-white/5 px-3 py-2 rounded-lg border border-white/5">
                      <span className="text-xs font-black text-slate-400">{s.symbol.replace('USDT','')}</span>
                      <span className={`text-xs font-black font-mono ${s.position!.unrealized_pnl_usd >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                        {s.position!.unrealized_pnl_usd >= 0 ? '+' : ''}${s.position!.unrealized_pnl_usd.toFixed(2)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
              
              <div className="bg-slate-900/50 p-6 rounded-2xl border border-white/5 min-w-[240px] text-right">
                <div className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest mb-1">Total P&L Estimado</div>
                <div className={`text-3xl font-black italic tracking-tighter ${totalPnL >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                  {totalPnL >= 0 ? '+' : ''}${totalPnL.toFixed(2)}
                </div>
                <div className={`text-xs font-bold ${totalPnL >= 0 ? 'text-emerald-500/70' : 'text-rose-500/70'}`}>
                  ({avgPnLPct >= 0 ? '+' : ''}{avgPnLPct.toFixed(2)}% promedio)
                </div>
                <div className="mt-4 pt-4 border-t border-white/5">
                   <div className="flex justify-between text-[0.55rem] font-black text-slate-500 uppercase mb-1.5">
                      <span>Uso de Capital Operativo</span>
                      <span>{capitalInUsePct.toFixed(0)}%</span>
                   </div>
                   <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                      <div className="h-full bg-blue-500 shadow-[0_0_10px_rgba(59,130,246,0.5)] transition-all duration-700" style={{ width: `${capitalInUsePct}%` }} />
                   </div>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {Object.entries(data.symbols).map(([sym, info]) => (
          <SymbolCard 
            key={sym} 
            symbol={sym} 
            data={info} 
            isSelected={selectedSymbol === sym}
            onSelect={() => setSelectedSymbol(sym)}
            onShowDiagnostic={(s) => setDiagnosticSymbol(s)}
          />
        ))}
      </div>

      {/* SECCIÓN 4 — Panel de Detalle (dinámico) */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-8 pb-10">
        <div className="xl:col-span-2 card glass-effect !p-0 overflow-hidden flex flex-col">
          <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/30 flex justify-between items-center">
            <div className="flex items-center gap-3">
              <span className="text-lg font-black tracking-tighter text-white">{selectedSymbol?.replace('USDT','')} / USDT</span>
              <span className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-widest">— Price Chart</span>
            </div>
            <div className="flex gap-1.5">
              {TIMEFRAMES.map(tf => (
                <button
                  key={tf.value}
                  onClick={() => setSelectedTf(tf.value)}
                  className={`px-3 py-1 rounded text-[0.65rem] font-black transition-all ${selectedTf === tf.value ? 'bg-blue-600 text-white shadow-[0_0_10px_rgba(37,99,235,0.4)]' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}
                >
                  {tf.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex-1 relative min-h-[450px]">
            {chartLoading && (
              <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950/40 backdrop-blur-sm">
                <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
              </div>
            )}
            <TradeMarkerChart 
              symbol={selectedSymbol || ''}
              timeframe={selectedTf}
              candles={candles}
              trades={trades}
              height={450}
              basis={currentFocus?.basis}
              upper_6={currentFocus?.upper_6}
              lower_6={currentFocus?.lower_6}
              activePosition={currentFocus?.position ? {
                avg_entry: currentFocus.position.avg_entry,
                sl_price: currentFocus.position.sl_price,
                tp_partial: currentFocus.position.tp_partial,
                tp_full: currentFocus.position.tp_full || currentFocus.upper_6,
              } : null}
            />
          </div>
          <div className="p-4 border-t border-slate-800 bg-slate-900/10 flex gap-6 overflow-x-auto whitespace-nowrap">
             <div className="flex items-center gap-2">
                <span className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest">TP AGN:</span>
                <span className="text-xs font-bold font-mono text-emerald-400">${currentFocus?.upper_6.toLocaleString()}</span>
             </div>
             <div className="flex items-center gap-2">
                <span className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest">TP CONS:</span>
                <span className="text-xs font-bold font-mono text-emerald-400/70">${currentFocus?.upper_5.toLocaleString()}</span>
             </div>
             <div className="flex items-center gap-2 border-l border-slate-800 pl-6">
                <span className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest">BASIS:</span>
                <span className="text-xs font-bold font-mono text-slate-300">${currentFocus?.basis.toLocaleString()}</span>
             </div>
             <div className="flex items-center gap-2">
                <span className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest">DIST:</span>
                <span className="text-xs font-bold font-mono text-blue-400">{currentFocus?.dist_basis_pct.toFixed(2)}%</span>
             </div>
          </div>
        </div>

        <div>
          {currentFocus?.position ? (
            <div className="card glass-effect border-emerald-500/20 h-full p-8 flex flex-col justify-between shadow-[0_0_50px_rgba(16,185,129,0.05)]">
              <div>
                <div className="flex justify-between items-center mb-8 pb-4 border-b border-white/5">
                   <h3 className="text-[0.65rem] font-black text-slate-500 uppercase tracking-[0.2em]">ANÁLISIS DE POSICIÓN ACTIVA</h3>
                   <span className="badge badge-green px-3 py-1 font-black italic shadow-[0_0_10px_rgba(16,185,129,0.2)]">
                     {currentFocus.position.side.toUpperCase()} × {currentFocus.position.trades_count} TRADE{currentFocus.position.trades_count > 1 ? 'S' : ''}
                   </span>
                </div>
                
                <div className="space-y-8">
                   {/* FILA 1: AVG ENTRY | UNREALIZED P&L */}
                   <div className="grid grid-cols-2 gap-4">
                      <div>
                         <label className="text-[0.55rem] text-slate-500 font-black uppercase tracking-widest block mb-1">Avg Entry Price</label>
                         <span className="text-xl font-black font-mono tracking-tighter text-white">${currentFocus.position.avg_entry.toLocaleString()}</span>
                      </div>
                      <div className="text-right">
                          <label className="text-[0.55rem] text-slate-500 font-black uppercase tracking-widest block mb-1">Unrealized P&L</label>
                          <div style={{
                            background: currentFocus.position.unrealized_pnl_usd < 0 ? '#3d0a0a' : '#0a3d2e',
                            borderRadius: '8px',
                            padding: '8px 12px',
                            textAlign: 'right',
                            display: 'inline-block'
                          }}>
                            <div style={{
                              color: currentFocus.position.unrealized_pnl_usd < 0 ? '#FF4757' : '#00C896',
                              fontSize: '1.4rem',
                              lineHeight: '1',
                              fontWeight: '900',
                              fontFamily: 'monospace'
                            }}>
                              {currentFocus.position.unrealized_pnl_usd >= 0 ? '+' : ''}${currentFocus.position.unrealized_pnl_usd.toFixed(2)}
                            </div>
                            <div style={{
                              color: currentFocus.position.unrealized_pnl_usd < 0 ? '#FF4757' : '#00C896',
                              fontSize: '0.85rem',
                              opacity: 0.8,
                              fontWeight: 'bold'
                            }}>
                              ({currentFocus.position.unrealized_pnl_pct >= 0 ? '+' : ''}{currentFocus.position.unrealized_pnl_pct.toFixed(2)}%)
                            </div>
                          </div>
                       </div>
                   </div>

                    {/* FILA 2: CURRENT SL | HOLDING TIME */}
                    <div className="grid grid-cols-2 gap-4">
                       <div className="bg-rose-500/5 p-3 rounded-xl border border-rose-500/10 relative overflow-hidden">
                          <label className="text-[0.55rem] text-rose-500/60 font-black uppercase tracking-widest block mb-1">Current SL</label>
                          <span className="text-lg font-black font-mono text-rose-500/90">${currentFocus.position.sl_price.toLocaleString()}</span>
                          {Math.abs((currentFocus.price - currentFocus.position.sl_price) / currentFocus.position.sl_price * 100) < 3.0 && (
                             <div className="absolute top-0 right-0 bg-rose-500 text-[0.5rem] font-black px-1.5 py-0.5 animate-pulse text-white uppercase">
                               ⚠️ SL CERCANO
                             </div>
                          )}
                       </div>
                       <div className="bg-white/5 p-3 rounded-xl border border-white/5 text-right">
                          <label className="text-[0.55rem] text-slate-500 font-black uppercase tracking-widest block mb-1">Holding Time</label>
                          <span className="text-lg font-black font-mono text-slate-300">
                            {currentFocus.position.bars_held}/{currentFocus.position.max_bars} <span className="text-[0.55rem] font-bold text-slate-500 uppercase">velas</span>
                          </span>
                       </div>
                    </div>

                   {/* FILA 3: NEXT BAND (DYNAMIC TP) */}
                   <div className="space-y-4">
                      <div className="bg-emerald-500/5 p-4 rounded-xl border border-emerald-500/20">
                         <label className="text-[0.55rem] text-emerald-500/60 font-black uppercase tracking-widest block mb-2">PRÓXIMA BANDA (TP DINÁMICO)</label>
                         {currentFocus.dynamic_tp ? (
                            <div className="space-y-3">
                               <div className="flex justify-between items-end">
                                  <span className="text-xl font-black font-mono text-white">
                                    ${currentFocus.dynamic_tp.next_target.target_price.toLocaleString()} — {currentFocus.dynamic_tp.next_target.target_name.toUpperCase()}
                                  </span>
                                  <span className="text-[0.6rem] font-bold text-slate-400">
                                    (a {Math.abs((currentFocus.price - currentFocus.dynamic_tp.next_target.target_price)/currentFocus.dynamic_tp.next_target.target_price*100).toFixed(1)}%)
                                  </span>
                                </div>
                                <div className="space-y-1 bg-black/20 p-2 rounded-lg border border-white/5">
                                  <div className="flex items-center gap-2 text-[0.6rem] font-bold text-rose-400">
                                     <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                                     Cerrar si: {currentFocus.mtf_score < 0 ? 'MTF < 0 (SÍ)' : 'MTF < 0'} o vela lápida IA
                                  </div>
                                  <div className="flex items-center gap-2 text-[0.6rem] font-bold text-emerald-400">
                                     <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                                     Mantener si: MTF &gt; 0.50 + IA alcista
                                  </div>
                               </div>
                               <div className="pt-2 border-t border-white/5">
                                  <span className="text-[0.6rem] font-black text-slate-500 uppercase block mb-1">DECISIÓN ACTUAL:</span>
                                  <p className="text-[0.65rem] font-bold text-white italic leading-relaxed">
                                     {currentFocus.dynamic_tp.decision.reason.replace('SI PRECIO PASA EL UPPER_5 SIN SEÑAL', 'Si supera UPPER_5 sin señal → UPPER_6')}
                                  </p>
                               </div>
                            </div>
                         ) : (
                            <span className="text-sm font-bold text-slate-600 italic">No disponible</span>
                         )}
                      </div>

                      <div className="bg-slate-800/30 p-4 rounded-xl border border-white/5">
                         <label className="text-[0.55rem] text-slate-500 font-black uppercase tracking-widest block mb-2">SIGUIENTE BANDA</label>
                         {currentFocus.dynamic_tp ? (
                            <div className="flex justify-between items-center">
                               <span className="text-sm font-black font-mono text-slate-300">
                                 ${currentFocus.dynamic_tp.after_next_target.target_price.toLocaleString()} — {currentFocus.dynamic_tp.after_next_target.target_name.toUpperCase()}
                               </span>
                               <span className="text-[0.55rem] font-bold text-slate-500 uppercase text-right">
                                 Si supera {currentFocus.dynamic_tp.next_target.target_name.toUpperCase()} sin señal → sig. nivel
                               </span>
                            </div>
                         ) : (
                            <span className="text-sm font-bold text-slate-600 italic">No disponible</span>
                         )}
                      </div>
                   </div>

                   {/* FILA 4: BREAK-EVEN | ZONA ACTUAL */}
                   <div className="grid grid-cols-2 gap-4 items-center">
                      <div className="flex items-center gap-2">
                         <div className={`w-2 h-2 rounded-full ${currentFocus.position.breakeven_hit ? 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]' : 'bg-slate-700'}`} />
                         <span className="text-[0.6rem] font-black text-slate-400 uppercase tracking-widest">Break-even: {currentFocus.position.breakeven_hit ? 'ACTIVADO' : 'NO'}</span>
                      </div>
                      <div className="text-right">
                         <span className="text-[0.6rem] font-black text-slate-400 uppercase tracking-widest">Zona Actual: </span>
                         <span className={`text-[0.65rem] font-black ${currentFocus.zone >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                           {currentFocus.zone > 0 ? `+${currentFocus.zone}` : currentFocus.zone}
                         </span>
                      </div>
                   </div>
 
                   {/* FILA 5: REGLA | MTF SCORE */}
                   <div className="grid grid-cols-2 gap-4 border-t border-white/5 pt-6">
                      <div>
                         <label className="text-[0.55rem] text-slate-500 font-black uppercase tracking-widest block mb-1">Regla Activada</label>
                         <span className={`text-xs font-black font-mono uppercase ${currentFocus.position.rule_code ? 'text-indigo-400' : 'text-slate-600'}`}>
                           {currentFocus.position.rule_code || '—'}
                         </span>
                      </div>
                      <div className="text-right">
                         <label className="text-[0.55rem] text-slate-500 font-black uppercase tracking-widest block mb-1">MTF Score</label>
                         <span className="text-xs font-black font-mono text-white">{currentFocus.mtf_score.toFixed(2)}</span>
                         <span className="ml-1 text-[0.6rem] font-black text-blue-400">→ BUY</span>
                      </div>
                   </div>
 
                   {/* FILA 6: RIESGO | SENTIMIENTO AI */}
                   <div className="grid grid-cols-1 gap-2 border-t border-white/5 pt-3">
                      <div className="flex justify-between items-center">
                         <div className="flex items-center gap-2">
                            <span className="text-sm">🟡</span>
                            <span className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest">AL ENTRAR: {(currentFocus.position as any).regime_entry?.toUpperCase() || '—'}</span>
                         </div>
                         <div className="flex items-center gap-2">
                            <span className="text-sm">🟡</span>
                            <span className="text-[0.6rem] font-black text-amber-500 uppercase tracking-widest">ACTUAL: {currentFocus.regime?.replace('riesgo_','').toUpperCase() || '—'}</span>
                         </div>
                      </div>
                      <div className="flex items-center gap-2 justify-end pt-2">
                         <span>😐</span>
                         <span className="text-[0.6rem] font-black text-slate-400 uppercase tracking-widest">SENTIMIENTO: {currentFocus.ai_sentiment?.toUpperCase() || 'NEUTRAL'}</span>
                      </div>
                   </div>
                </div>
              </div>

              {/* FILA 7: BOTONES ACCIÓN */}
              <div className="space-y-4 mt-12">
                <div className="flex gap-2 mb-2">
                   <div className="flex-1 h-1 bg-emerald-500/10 rounded-full overflow-hidden">
                      <div className="h-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.3)] transition-all duration-500" style={{ width: `${Math.min((currentFocus.position.bars_held/currentFocus.position.max_bars)*100, 100)}%` }} />
                   </div>
                </div>
                <div className="flex gap-3">
                   <button className="flex-1 btn btn-ghost !py-4 !text-[0.6rem] font-black border-slate-800 hover:bg-rose-500/10 hover:border-rose-500/20 hover:text-rose-500 transition-all uppercase tracking-widest">CERRAR MANUAL</button>
                   <button className="flex-1 btn btn-primary !py-4 !text-[0.6rem] font-black !bg-emerald-600 border-none shadow-[0_0_20px_rgba(16,185,129,0.2)] hover:!bg-emerald-500 uppercase tracking-widest">FORCE TP NEXT LVL</button>
                </div>
              </div>
            </div>
          ) : (
            <div className="card glass-effect border-slate-800/50 h-full p-8 flex flex-col items-center justify-center text-center opacity-60">
               <span className="text-4xl mb-6 grayscale text-slate-700">💼</span>
               <h3 className="text-xs font-black text-slate-500 uppercase tracking-widest mb-2">Sin Posición Activa</h3>
               <p className="text-sm font-medium text-slate-600 italic">Esperando señal válida para {selectedSymbol}</p>
            </div>
          )}
        </div>
      </div>

      {/* SECCIÓN 5 — Signals y Spikes */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
         <TableCard title="Recent Trading Signals" data={data.recent_signals} type="signals" />
         <TableCard title="Market Feed (Spikes)" data={data.market_feed} type="spikes" />
      </div>

      {diagnosticSymbol && (
        <RuleDiagnosticPanel 
          symbol={diagnosticSymbol} 
          onClose={() => setDiagnosticSymbol(null)} 
        />
      )}

      <style jsx>{`
        .glass-effect {
          background: rgba(17, 24, 39, 0.4);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
          border: 1px solid rgba(255, 255, 255, 0.04);
        }
      `}</style>
    </div>
  )
}

function MetricCard({ label, value, color }: { label: string, value: string, color: string }) {
  return (
    <div className="card glass-effect border-slate-800/50 p-6">
      <span className="text-[0.65rem] font-black text-slate-500 uppercase tracking-[.25em] block mb-2">{label}</span>
      <span className={`text-3xl font-black italic tracking-tighter ${color}`}>{value}</span>
    </div>
  )
}

function SymbolCard({ 
  symbol, 
  data, 
  isSelected, 
  onSelect,
  onShowDiagnostic
}: { 
  symbol: string, 
  data: SymbolData, 
  isSelected: boolean, 
  onSelect: () => void,
  onShowDiagnostic: (sym: string) => void
}) {
  const getStatusColor = () => {
    switch(data.card_status) {
      case 'active': return 'border-emerald-500/50 ring-1 ring-emerald-500/20 shadow-[0_0_15px_rgba(16,185,129,0.1)]'
      case 'emergency': return 'border-rose-500 !bg-rose-500/5 animate-pulse'
      case 'signal': return 'border-amber-500/50'
      default: return isSelected ? 'border-blue-500/40 bg-blue-500/5' : 'border-slate-800/60'
    }
  }

  const getStatusIcon = () => {
    switch(data.card_status) {
      case 'active': return <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
      case 'emergency': return <span>🚨</span>
      case 'signal': return <span>⚡</span>
      default: return (
        data.mtf_score > 0.35 ? <div className="w-2 h-2 rounded-full bg-blue-500 shadow-[0_0_8px_rgba(59,130,246,0.5)]" /> : 
        <div className="w-2 h-2 rounded-full bg-slate-600" />
      )
    }
  }

  const getADXLabel = (adx: number) => {
    if (adx >= 50) return { label: 'EXPLOSIVO', arrow: '↑↑', threshold: 0.55, color: 'text-rose-400' }
    if (adx >= 35) return { label: 'AGRESIVO',  arrow: '↑',  threshold: 0.45, color: 'text-amber-400' }
    if (adx >= 20) return { label: 'MODERADO',  arrow: '→',  threshold: 0.35, color: 'text-blue-400' }
    return               { label: 'DÉBIL',      arrow: '↓',  threshold: 0.20, color: 'text-emerald-400' }
  }



  const getRegimeLabel = (regime: string) => {
    const r = regime.toLowerCase()
    if (r.includes('bajo')) return 'Suelo / Bajo'
    if (r.includes('medio')) return 'Neutral / Medio'
    if (r.includes('agresivo')) return 'Agresivo / Alto'
    return 'Neutral'
  }

  const getVolBandLabel = (rel: number) => {
    if (rel <= 0.30) return { label: 'BAJO', color: 'text-rose-400' }
    if (rel <= 0.60) return { label: 'MEDIO', color: 'text-amber-400' }
    return { label: 'ALTO', color: 'text-emerald-400' }
  }
  const adxInfo = getADXLabel(data.adx)
  const volInfo = getVolBandLabel(data.volume_rel || 0)
  const volThreshold = data.sar_phase === 'long' ? 0.40 : 0.60

  const getObservationLabel = () => {
    if (data.card_status === 'active') return 'POSICIÓN ACTIVA'
    if (data.spike?.detected) return '⚡ VOLUMEN INUSUAL'
    if (data.mtf_score > 0.35) return '🔍 BUSCANDO ENTRADA'
    return '⏳ ESPERANDO SEÑAL'
  }

  return (
    <div 
      onClick={onSelect}
      className={`card glass-effect !p-5 cursor-pointer transition-all duration-300 hover:scale-[1.02] ${getStatusColor()}`}
    >
      <div className="flex justify-between items-start mb-5">
        <div className="flex items-center gap-2">
           {getStatusIcon()}
           <span className="text-lg font-black tracking-tighter">{symbol.replace('USDT', '')}</span>
        </div>
        <span className={`text-[0.65rem] font-black italic ${data.zone >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
          Zone {data.zone > 0 ? `+${data.zone}` : data.zone}
        </span>
      </div>

      {/* --- SAR 4H MACD FILTER --- */}
      <div className="mb-4">
        {data.sar_phase === 'long' ? (
          <div className="flex items-center gap-2 bg-emerald-500/10 border border-emerald-500/20 px-2 py-1 rounded">
             <span className="text-[0.65rem] font-black text-emerald-500 italic">🟢 FASE LONG (SAR 4h)</span>
          </div>
        ) : data.sar_phase === 'short' ? (
          <div className="flex items-center gap-2 bg-rose-500/10 border border-rose-500/20 px-2 py-1 rounded">
             <span className="text-[0.65rem] font-black text-rose-500 italic">🔴 FASE SHORT (SAR 4h)</span>
          </div>
        ) : (
          <div className="flex items-center gap-2 bg-slate-500/10 border border-slate-500/20 px-2 py-1 rounded">
             <span className="text-[0.65rem] font-black text-slate-500 italic">⚪ FASE NEUTRAL (SAR)</span>
          </div>
        )}
        
        {/* Changed recently alert */}
        {(() => {
          if (!data.sar_phase_changed_at) return null;
          const changedDate = new Date(data.sar_phase_changed_at);
          const diffMs = new Date().getTime() - changedDate.getTime();
          if (diffMs < 15 * 60 * 1000) { // 15 mins
            return (
              <div className="mt-1 flex items-center justify-center gap-2 bg-blue-500 px-2 py-1 rounded animate-pulse">
                <span className="text-[0.6rem] font-black text-white italic">🔄 SAR CAMBIÓ → {data.sar_phase?.toUpperCase()}</span>
              </div>
            );
          }
          return null;
        })()}
      </div>

      <div className="space-y-4">
        <div className="flex justify-between items-end">
           <span className="text-xl font-black font-mono tracking-tighter">${data.price.toLocaleString()}</span>
           <span 
             className={`text-[0.6rem] font-bold uppercase tracking-widest px-2 py-0.5 rounded ${
               data.card_status === 'active' ? 'text-emerald-400' : 
               data.mtf_score > 0.35 ? 'text-blue-400 bg-blue-500/10' : 'text-slate-500'
             }`}
           >
             {getObservationLabel()}
           </span>
        </div>

        {data.card_status === 'active' && data.position ? (
          <div className="pt-4 border-t border-slate-800/50 space-y-3">
              <div className="flex justify-between items-center bg-black/20 p-2 rounded-lg">
                 <span className="badge badge-green text-[0.55rem] font-black uppercase tracking-tighter">
                   {data.position.side.toUpperCase()} x{data.position.trades_count} TRADES
                 </span>
                 <div className="px-3 py-1.5 rounded-md flex flex-col items-end" style={{ backgroundColor: data.position.unrealized_pnl_usd >= 0 ? '#0a3d2e' : '#3d0a0a' }}>
                    <span className="text-[1.1rem] font-black tracking-tighter leading-none" style={{ color: data.position.unrealized_pnl_usd >= 0 ? '#00C896' : '#FF4757' }}>
                      {data.position.unrealized_pnl_usd >= 0 ? '+' : ''}${data.position.unrealized_pnl_usd.toFixed(2)}
                    </span>
                    <span className="text-[0.65rem] font-black opacity-80 leading-none mt-0.5" style={{ color: data.position.unrealized_pnl_usd >= 0 ? '#00C896' : '#FF4757' }}>
                      {data.position.unrealized_pnl_pct >= 0 ? '+' : ''}{data.position.unrealized_pnl_pct.toFixed(2)}%
                    </span>
                 </div>
              </div>
             <div className="flex justify-between text-[0.6rem] font-bold text-slate-500 uppercase tracking-widest">
                <span>SL: ${data.position.sl_price.toLocaleString()}</span>
                <span>{data.position.bars_held}/{data.position.max_bars} VELAS</span>
             </div>
             
             {/* SL PROXIMITY ALERT badge */}
             {(() => {
                const dist = Math.abs((data.price - data.position.sl_price) / data.position.sl_price * 100);
                if (dist < 3.0) {
                  return (
                    <div className="bg-[#FF4757] text-white px-2 py-1 rounded text-[0.65rem] font-black animate-pulse flex items-center justify-center gap-1 shadow-[0_0_15px_rgba(255,71,87,0.4)]">
                      ⚠️ SL CERCANO {dist.toFixed(1)}%
                    </div>
                  );
                }
                return null;
             })()}
             <div className="flex justify-between items-center pt-1">
                <div className="flex items-center gap-1.5 grayscale-0">
                   <span>{data.ai_sentiment === 'bullish' ? '🟢' : data.ai_sentiment === 'bearish' ? '🔴' : '😐'}</span>
                   <span className="text-[0.6rem] font-black text-slate-400 uppercase tracking-widest">{data.ai_sentiment?.toUpperCase() || 'NEUTRAL'}</span>
                </div>
                <span className="text-[0.6rem] font-black text-blue-400 uppercase tracking-widest">MTF: {data.mtf_score.toFixed(2)}</span>
             </div>
          </div>
        ) : data.card_status === 'signal' && data.spike?.detected ? (
          <div className="pt-4 border-t border-amber-500/30 space-y-2">
             <div className="flex justify-between text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">
                <span>Spike Ratio:</span>
                <span className="text-amber-400 font-mono">{(data.spike.ratio * 100).toFixed(1)}%</span>
             </div>
             <div className="flex justify-between items-center">
                <span className="text-[0.65rem] font-bold text-slate-400 uppercase tracking-widest">Bloqueado:</span>
                <span className="text-[0.6rem] font-black text-amber-500 uppercase italic">
                  {data.last_signal?.blocked_reason || 'Spike detectado'}
                </span>
             </div>
          </div>
        ) : (
          <div className="pt-3 border-t border-white/5 space-y-4">
             {/* --- SECCION SCALPING --- */}
             <div className="space-y-2">
                <div className="flex items-center gap-2 border-b border-white/5 pb-1">
                   <div className="w-1 h-3 bg-blue-500 rounded-full" />
                   <span className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest">Scalping Signals</span>
                </div>
                <div className="space-y-1.5 px-1">
                   <div className="flex justify-between items-center text-[0.6rem] font-bold">
                      <span className="text-slate-500">MTF Score</span>
                      <span className={data.mtf_score >= adxInfo.threshold ? 'text-emerald-400' : 'text-slate-400'}>
                        {data.mtf_score.toFixed(2)} <span className="text-[0.5rem] opacity-50">/ {adxInfo.threshold}</span>
                      </span>
                   </div>
                   <div className="flex justify-between items-center text-[0.6rem] font-bold">
                      <span className="text-slate-500">Velocidad</span>
                      <span className={adxInfo.color}>
                        {adxInfo.label} <span className="text-[0.5rem] opacity-50">(ADX {data.adx.toFixed(1)})</span>
                      </span>
                   </div>
                   <div className="flex justify-between items-center text-[0.6rem] font-bold">
                      <span className="text-slate-500">Vol. Rel (<span className={volInfo.color}>{volInfo.label}</span>)</span>
                      <span className={(data.volume_rel || 0) >= volThreshold ? 'text-emerald-400' : 'text-slate-400'}>
                         {((data.volume_rel || 0)*100).toFixed(0)}% <span className="text-[0.5rem] opacity-50">/ {(volThreshold*100).toFixed(0)}%</span>
                      </span>
                   </div>
                   <div className="flex justify-between items-center text-[0.6rem] font-bold">
                      <span className="text-slate-500">Dist. Basis</span>
                      <span className={data.dist_basis_pct <= 2.2 ? 'text-emerald-400' : 'text-rose-400'}>
                         {data.dist_basis_pct.toFixed(2)}% <span className="text-[0.5rem] opacity-50">/ 2.2%</span>
                      </span>
                   </div>
                </div>
             </div>

             {/* --- SECCION SWING --- */}
             <div className="space-y-2 pt-1">
                <div className="flex items-center gap-2 border-b border-white/5 pb-1">
                   <div className="w-1 h-3 bg-indigo-500 rounded-full" />
                   <span className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest">Swing Strategy</span>
                </div>
                <div className="space-y-1.5 px-1">
                   <div className="flex justify-between items-center text-[0.6rem] font-bold">
                      <span className="text-slate-500">Bands Health</span>
                      <div className="flex items-center gap-1.5">
                         <div className={`w-2 h-2 rounded-full ${data.upper_6 > 0 ? 'bg-emerald-500 shadow-[0_0_5px_rgba(16,185,129,0.5)]' : 'bg-amber-500 animate-pulse'}`} />
                         <span className={data.upper_6 > 0 ? 'text-emerald-400' : 'text-amber-400'}>
                            {data.upper_6 > 0 ? 'MATURE / READY' : 'LOADING DATA...'}
                         </span>
                      </div>
                   </div>
                   <div className="flex justify-between items-center text-[0.6rem] font-bold">
                      <span className="text-slate-500">ADX (<span className={adxInfo.color}>{adxInfo.label}</span>)</span>
                      <span className="text-white">{data.adx.toFixed(1)} <span className="text-[0.5rem] opacity-50">umbral: {adxInfo.threshold}</span></span>
                   </div>
                </div>
             </div>

             {/* --- FOOTER CARD --- */}
             <div className="flex justify-between items-center pt-2 border-t border-white/5">
                <div className="flex items-center gap-1.5">
                   <span className="text-[0.65rem]">{data.ai_sentiment === 'bullish' ? '🟢' : data.ai_sentiment === 'bearish' ? '🔴' : '😐'}</span>
                   <span className="text-[0.6rem] font-black text-slate-400 uppercase tracking-widest">
                     {getRegimeLabel(data.regime || 'neutral').toUpperCase()}
                   </span>
                </div>
                <span className={`text-[0.6rem] font-black italic ${data.zone >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
                  ZONA {data.zone > 0 ? `+${data.zone}` : data.zone}
                </span>
             </div>
          </div>
        )}
      </div>

      <button className={`w-full mt-6 py-2.5 rounded-lg text-[0.6rem] font-black uppercase tracking-[0.2em] transition-all ${isSelected ? 'bg-blue-600 text-white shadow-[0_0_15px_rgba(37,99,235,0.3)]' : 'bg-slate-800/50 text-slate-400 hover:bg-slate-800'}`}>
        {isSelected ? 'EN FOCO' : 'Ver Detalle'}
      </button>

      <button
        onClick={(e) => {
          e.stopPropagation();
          onShowDiagnostic(symbol);
        }}
        style={{
          width:        '100%',
          padding:      '8px 0',
          marginTop:    '8px',
          background:   'rgba(255,255,255,0.03)',
          border:       '1px solid rgba(255,255,255,0.06)',
          borderRadius: '8px',
          color:        '#666',
          fontSize:     '11px',
          fontWeight:   900,
          letterSpacing: '1.5px',
          cursor:       'pointer',
          display:      'flex',
          alignItems:   'center',
          justifyContent: 'center',
          gap:          '8px',
          transition:   'all 0.2s cubic-bezier(0.17, 0.67, 0.83, 0.67)',
        }}
        onMouseEnter={e => {
          e.currentTarget.style.background = 'rgba(255,255,255,0.08)'
          e.currentTarget.style.color = '#FFF'
          e.currentTarget.style.borderColor = 'rgba(0,200,150,0.3)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = 'rgba(255,255,255,0.03)'
          e.currentTarget.style.color = '#666'
          e.currentTarget.style.borderColor = 'rgba(255,255,255,0.06)'
        }}
      >
        🔍 DIAGNÓSTICO DE REGLAS
      </button>
    </div>
  )
}

function TableCard({ title, data, type }: { title: string, data: any[], type: 'signals' | 'spikes' }) {
  return (
    <div className="card glass-effect p-0 overflow-hidden">
      <div className="px-6 py-4 border-b border-slate-800 bg-slate-900/30 flex justify-between items-center">
         <h3 className="text-xs font-black text-slate-400 uppercase tracking-widest">{title}</h3>
      </div>
      <div className="table-container">
        <table>
          <thead>
            {type === 'signals' ? (
              <tr>
                <th>Symbol</th>
                <th>Fecha y Hora</th>
                <th>Direction</th>
                <th>Score</th>
                <th>Status</th>
              </tr>
            ) : (
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Ratio</th>
                <th>Zone</th>
                <th>Action</th>
              </tr>
            )}
          </thead>
          <tbody>
            {(data && data.length > 0) ? data.slice(0, 5).map((item, idx) => (
              <tr key={idx}>
                {type === 'signals' ? (
                  <>
                    <td className="font-bold text-white">{item.symbol}</td>
                    <td className="text-[0.65rem] font-mono text-blue-400">
                      {new Date(item.created_at).toLocaleString('es-PE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td><span className={`badge ${item.signal_type === 'BUY' ? 'badge-green' : 'badge-red'}`}>{item.signal_type}</span></td>
                    <td className="font-mono text-sm">{(item.score_final || 0).toFixed(2)}</td>
                    <td><span className="badge badge-green">EXECUTED</span></td>
                  </>
                ) : (
                  <>
                    <td className="text-[0.65rem] font-mono text-slate-500">
                      {new Date(item.detected_at).toLocaleString('es-PE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="font-bold text-white">{item.symbol}</td>
                    <td className="text-blue-400 font-bold">{parseFloat(item.total_spike_ratio || item.spike_ratio || 0).toFixed(1)}x</td>
                    <td><span className="text-xs text-slate-400">
                      {item.zone !== undefined && item.zone !== null 
                        ? `Zone ${item.zone >= 0 ? '+' : ''}${item.zone}` 
                        : (item.mtf_score !== undefined && item.mtf_score !== null 
                            ? `Zone ${item.mtf_score >= 0 ? '+' : ''}${item.mtf_score}` 
                            : '—')}
                    </span></td>
                    <td><span className="text-[0.65rem] font-bold text-amber-500">MONITORING</span></td>
                  </>
                )}
              </tr>
            )) : (
              <tr>
                <td colSpan={5} className="text-center py-10 text-slate-500 italic">No hay datos recientes.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
