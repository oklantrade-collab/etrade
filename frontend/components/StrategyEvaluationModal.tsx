'use client'
import React, { useState, useEffect } from 'react'
import { supabase } from '@/lib/supabase'

interface ConditionDetail {
  name: string
  passed: boolean
  weight: number
  current_value: any
  target_value: any
  operator: string
}

interface RuleEvaluation {
  rule_code: string
  rule_name: string
  direction: string
  score: number
  triggered: boolean
  conditions: Record<string, ConditionDetail>
}

interface EvaluationData {
  scalping: {
    long: RuleEvaluation[]
    short: RuleEvaluation[]
  }
  swing: {
    long: RuleEvaluation[]
    short: RuleEvaluation[]
  }
}

export default function StrategyEvaluationModal({ 
  isOpen, 
  onClose, 
  symbol 
}: { 
  isOpen: boolean, 
  onClose: () => void,
  symbol: string
}) {
  const [timeframe, setTimeframe] = useState('15m')
  const [data, setData] = useState<EvaluationData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (isOpen && symbol) {
      fetchEvaluation()
    }
  }, [isOpen, symbol, timeframe])

  async function fetchEvaluation() {
    setLoading(true)
    try {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || '/api/v1'
      const res = await fetch(`${baseUrl}/strategies/live/${symbol}?timeframe=${timeframe}`)
      const json = await res.json()
      
      // Transformar lista plana de reglas al formato agrupado esperado por la UI
      const groupedData: EvaluationData = {
        scalping: { long: [], short: [] },
        swing: { long: [], short: [] }
      }

      if (json.rules) {
        json.rules.forEach((r: any) => {
          const type = r.strategy_type === 'scalping' ? 'scalping' : 'swing'
          const dir = r.direction === 'long' ? 'long' : 'short'
          groupedData[type][dir].push({
            rule_code: r.rule_code,
            rule_name: r.rule_name,
            direction: r.direction,
            score: r.score,
            triggered: r.triggered,
            conditions: r.conditions
          })
        })
      }
      
      // Inyectar el contexto original para los headers
      (groupedData as any).context = json.context
      setData(groupedData)
    } catch (err) {
      console.error("Error fetching detailed evaluation:", err)
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  const calculateDelta = (current: any, target: any) => {
    if (typeof current !== 'number' || typeof target !== 'number') return { pct: 'N/A', num: 'N/A' }
    if (target === 0) return { pct: '0%', num: (current - target).toFixed(4) }
    const deltaNum = current - target
    const deltaPct = (deltaNum / target) * 100
    return {
      pct: `${deltaPct > 0 ? '+' : ''}${deltaPct.toFixed(2)}%`,
      num: `${deltaNum > 0 ? '+' : ''}${deltaNum.toFixed(4)}`
    }
  }

  const renderSection = (title: string, rules: RuleEvaluation[]) => (
    <div className="space-y-4">
      <h3 className="text-sm font-bold text-slate-500 uppercase tracking-widest border-l-2 border-blue-500 pl-3">{title}</h3>
      {rules.length === 0 ? (
        <div className="text-slate-600 text-xs italic py-2">No hay reglas aplicables para esta dirección/timeframe.</div>
      ) : (
        <div className="space-y-3">
          {rules.map((rule) => {
            const allConditions = Object.values(rule.conditions)
            return (
              <div key={rule.rule_code} className="bg-[#1e2536] border border-slate-800 rounded-xl overflow-hidden shadow-lg">
                <div className="px-4 py-3 bg-slate-800/20 flex justify-between items-center group cursor-pointer">
                  <div className="flex items-center gap-3">
                    <span className={`px-2 py-0.5 rounded text-[0.6rem] font-black uppercase ${rule.direction === 'long' ? 'bg-emerald-500/10 text-emerald-500' : 'bg-rose-500/10 text-rose-500'}`}>
                      {rule.rule_code}
                    </span>
                    <h4 className="text-sm font-semibold text-slate-200">{rule.rule_name}</h4>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <span className="text-[0.6rem] text-slate-500 block uppercase font-bold">Score</span>
                      <span className={`text-xs font-mono font-bold ${rule.triggered ? 'text-emerald-400' : 'text-amber-400'}`}>
                        {(rule.score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className={`px-3 py-1 rounded-full text-[0.65rem] font-bold ${rule.triggered ? 'bg-emerald-500/20 text-emerald-500 border border-emerald-500/30' : 'bg-slate-700/50 text-slate-400 border border-slate-700'}`}>
                      {rule.triggered ? 'CUMPLE' : 'NO CUMPLE'}
                    </div>
                  </div>
                </div>

                <div className="p-0">
                  <table className="w-full text-left text-[0.7rem] border-collapse">
                    <thead>
                      <tr className="bg-slate-900/30 text-slate-500 border-b border-slate-800/50">
                        <th className="px-4 py-2 font-bold uppercase tracking-tighter">Condición</th>
                        <th className="px-4 py-2 font-bold uppercase tracking-tighter text-right">Peso</th>
                        <th className="px-4 py-2 font-bold uppercase tracking-tighter text-right">Actual</th>
                        <th className="px-4 py-2 font-bold uppercase tracking-tighter text-right">Objetivo</th>
                        <th className="px-4 py-2 font-bold uppercase tracking-tighter text-right">Falta (%)</th>
                        <th className="px-4 py-2 font-bold uppercase tracking-tighter text-right">Falta (num)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/30">
                      {allConditions.map((cond, idx) => {
                        const delta = calculateDelta(cond.current_value, cond.target_value)
                        return (
                          <tr key={idx} className={`hover:bg-slate-800/10 transition-colors ${cond.passed ? '' : 'bg-rose-500/5'}`}>
                            <td className="px-4 py-2 text-slate-300 font-medium">
                              <div className="flex items-center gap-2">
                                <span className={cond.passed ? 'text-emerald-500' : 'text-rose-500'}>
                                  {cond.passed ? '✓' : '✗'}
                                </span>
                                {cond.name}
                              </div>
                            </td>
                            <td className="px-4 py-2 text-right font-mono text-slate-500 font-bold">
                              {Math.round(cond.weight * 100)}%
                            </td>
                            <td className="px-4 py-2 text-right font-mono text-slate-400">
                              {typeof cond.current_value === 'number' ? cond.current_value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(cond.current_value)}
                            </td>
                            <td className="px-4 py-2 text-right font-mono text-slate-200">
                              <span className="text-slate-500 mr-1">{cond.operator}</span>
                              {typeof cond.target_value === 'number' ? cond.target_value.toLocaleString(undefined, { maximumFractionDigits: 6 }) : String(cond.target_value)}
                            </td>
                            <td className={`px-4 py-2 text-right font-mono ${cond.passed ? 'text-slate-600' : (delta.pct.startsWith('+') ? 'text-emerald-500/60' : 'text-rose-500/60')}`}>
                              {cond.passed ? '---' : delta.pct}
                            </td>
                            <td className={`px-4 py-2 text-right font-mono ${cond.passed ? 'text-slate-600' : (delta.num.startsWith('+') ? 'text-emerald-500/60' : 'text-rose-500/60')}`}>
                              {cond.passed ? '---' : delta.num}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )

  return (
    <div className="fixed inset-0 z-[150] flex items-center justify-center p-4 bg-black/80 backdrop-blur-md">
      <div className="bg-[#121721] border border-slate-700 w-full max-w-6xl max-h-[92vh] rounded-3xl shadow-[0_0_50px_rgba(0,0,0,0.5)] flex flex-col overflow-hidden animate-in fade-in zoom-in duration-200">
        
        {/* Header Profundo */}
        <div className="px-8 py-6 border-b border-slate-800 bg-gradient-to-r from-slate-900 via-[#121721] to-slate-900 flex justify-between items-center">
          <div className="flex items-center gap-6">
            <div className="h-12 w-12 rounded-2xl bg-blue-600/20 flex items-center justify-center border border-blue-500/30 text-blue-500 font-black text-2xl shadow-[0_0_20px_rgba(59,130,246,0.2)]">
              {symbol.substring(0, 1)}
            </div>
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-2xl font-black text-white tracking-tight">{symbol}</h2>
                <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 text-[0.6rem] font-bold tracking-widest border border-slate-700">LIVE ENGINE</span>
              </div>
              <p className="text-xs text-slate-500 font-medium mt-1">Análisis profundo de reglas de entrada y salida v5.0 (Experimental)</p>
            </div>
          </div>
          
          <div className="flex items-center gap-6">
            <div className="flex bg-[#1a202c] p-1 rounded-xl border border-slate-700/50 shadow-inner">
              {['5m', '15m', '30m', '4h'].map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-4 py-1.5 rounded-lg text-[0.7rem] font-bold transition-all duration-200 ${timeframe === tf ? 'bg-blue-600 text-white shadow-lg' : 'text-slate-500 hover:text-slate-300'}`}
                >
                  {tf}
                </button>
              ))}
            </div>
            <button 
              onClick={onClose} 
              className="h-10 w-10 flex items-center justify-center hover:bg-rose-500/20 hover:text-rose-500 text-slate-500 rounded-full transition-all border border-transparent hover:border-rose-500/30 active:scale-90"
            >
              <span className="text-2xl leading-none">&times;</span>
            </button>
          </div>
        </div>
        
        {/* Market Context Summary (NUEVO) */}
        <div className="px-8 py-3 bg-slate-800/20 border-b border-slate-800 flex gap-6 text-[0.65rem] overflow-x-auto whitespace-nowrap scrollbar-hide">
          <div className="flex flex-col">
            <span className="text-slate-500 font-bold uppercase tracking-widest">MTF Score</span>
            <span className={`font-mono font-bold ${(data as any)?.context?.mtf_score > 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
              {(data as any)?.context?.mtf_score?.toFixed(2) || '0.00'}
            </span>
          </div>
          <div className="w-px h-6 bg-slate-800 my-auto" />
          <div className="flex flex-col">
            <span className="text-slate-500 font-bold uppercase tracking-widest">Trend ADX</span>
            <span className="text-slate-300 font-bold">{(data as any)?.context?.adx?.toFixed(1) || '0.0'} ({(data as any)?.context?.adx_velocity || '---'})</span>
          </div>
          <div className="w-px h-6 bg-slate-800 my-auto" />
          <div className="flex flex-col">
            <span className="text-slate-500 font-bold uppercase tracking-widest">SAR 4h</span>
            <span className={`font-bold ${(data as any)?.context?.sar_trend_4h > 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
              {(data as any)?.context?.sar_trend_4h > 0 ? 'LONG' : 'SHORT'}
            </span>
          </div>
          <div className="w-px h-6 bg-slate-800 my-auto" />
          <div className="flex flex-col">
            <span className="text-slate-500 font-bold uppercase tracking-widest">Retro / Range (OR)</span>
            <span className={`font-bold ${(data as any)?.context?.is_range_or_fall ? 'text-blue-400' : 'text-rose-500'}`}>
              {(data as any)?.context?.is_range_or_fall ? 'ACTIVO' : 'INACTIVO'}
            </span>
          </div>
          <div className="w-px h-6 bg-slate-800 my-auto" />
          <div className="flex flex-col">
            <span className="text-slate-500 font-bold uppercase tracking-widest">Pine Signal</span>
            <span className={`font-bold ${(data as any)?.context?.pinescript_signal === 'Buy' ? 'text-emerald-500' : (data as any)?.context?.pinescript_signal === 'Sell' ? 'text-rose-500' : 'text-slate-500'}`}>
              {(data as any)?.context?.pinescript_signal || 'NONE'}
            </span>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-8 custom-scrollbar bg-[#0d1117] space-y-10">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-32 space-y-6">
              <div className="h-12 w-12 border-4 border-blue-500/20 border-t-blue-500 rounded-full animate-spin shadow-inner"></div>
              <div className="text-slate-500 animate-pulse font-mono text-sm tracking-widest uppercase">Evaluando condiciones de mercado...</div>
            </div>
          ) : data ? (
            <>
              {/* SCALPING SECTION */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {renderSection("Scalping (Long)", data.scalping.long)}
                {renderSection("Scalping (Short)", data.scalping.short)}
              </div>

              <div className="h-px bg-slate-800/50 shadow-sm w-full"></div>

              {/* SWING SECTION */}
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
                {renderSection("Swing Trade (Long)", data.swing.long)}
                {renderSection("Swing Trade (Short)", data.swing.short)}
              </div>
            </>
          ) : (
            <div className="text-center py-20 bg-rose-500/5 border border-rose-500/20 rounded-2xl">
              <span className="text-rose-500 font-bold block mb-2 text-lg">DATOS NO DISPONIBLES</span>
              <p className="text-slate-500 text-sm">No se pudo cargar la evaluación para este símbolo.</p>
              <button onClick={fetchEvaluation} className="mt-6 btn btn-primary px-8">Reintentar</button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-8 py-4 border-t border-slate-800 bg-slate-900/60 flex justify-between items-center">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"></div>
              <span className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-tighter">Socket Online</span>
            </div>
            <div className="text-[0.65rem] text-slate-500">
              Ult. Actualización: <span className="text-slate-400 font-mono">{new Date().toLocaleTimeString()}</span>
            </div>
          </div>
          <div className="flex gap-3">
             <button className="px-6 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-bold rounded-xl transition-all border border-slate-700" onClick={onClose}>Cerrar Inspección</button>
             <button className="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white text-xs font-extrabold rounded-xl shadow-lg shadow-blue-600/20 transition-all active:scale-95" onClick={fetchEvaluation}>Refrescar Simulación</button>
          </div>
        </div>
      </div>

      <style jsx>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 8px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(15, 23, 42, 0.1);
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #1e293b;
          border-radius: 20px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: #334155;
        }
      `}</style>
    </div>
  )
}
