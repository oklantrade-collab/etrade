'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'

interface StrategyRule {
  rule_code: string
  name: string
  strategy_type: string
  direction: string
  cycle: string
  applicable_cycles: string[]
  min_score: number
  confidence: string
  enabled: boolean
  notes?: string
  condition_ids: number[]
  condition_weights: Record<string, number>
  evaluaciones_24h: number
  activaciones_24h: number
  score_promedio_24h: number
}

interface LiveEval {
  symbol: string
  best_opportunity: {
    rule_code: string
    direction: string
    score: number
    min_score: number
    triggered: boolean
    conditions_passed: string[]
    conditions_failed: string[]
    cycle?: string
  } | null
  near_misses: {
    rule_code: string
    score: number
    missing: string[]
  }[]
}

interface Condition {
  id: number
  name: string
  variable?: {
    source_field: string
  }
}

const CYCLE_COLORS: Record<string, { bg: string, text: string }> = {
  '5m':  { bg: '#1a3a5c', text: '#4FC3F7' },
  '15m': { bg: '#1a3a2a', text: '#00C896' },
  '4h':  { bg: '#3a1a3a', text: '#CE93D8' },
  '1d':  { bg: '#3a2a1a', text: '#FFB74D' },
}

const AVAILABLE_CYCLES = ['5m', '15m', '4h', '1d']

export default function StrategiesPage() {
  const [rules, setRules] = useState<StrategyRule[]>([])
  const [liveEvals, setLiveEvals] = useState<Record<string, LiveEval>>({})
  const [loading, setLoading] = useState(true)
  const [symbols, setSymbols] = useState<string[]>(['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT'])
  const [conditions, setConditions] = useState<Condition[]>([])
  
  // Tabs state
  const [activeTab, setActiveTab] = useState<'scalping' | 'swing' | 'live'>('scalping')
  const [activeDir, setActiveDir] = useState<'long' | 'short'>('long')
  
  // Modal state
  const [editingRule, setEditingRule] = useState<StrategyRule | null>(null)

  useEffect(() => {
    loadRules()
    loadConditions()
    loadLiveEvals()
    const interval = setInterval(loadLiveEvals, 15000) // Refresh live every 15s
    return () => clearInterval(interval)
  }, [])

  async function loadRules() {
    try {
      const res = await fetch('/api/v1/strategies/rules')
      if (res.ok) {
        setRules(await res.json())
      }
    } catch (err) {
      console.error('Error loading rules:', err)
    } finally {
      setLoading(false)
    }
  }

  async function loadConditions() {
    try {
      const res = await fetch('/api/v1/strategies/conditions')
      if (res.ok) {
        setConditions(await res.json())
      }
    } catch (err) {
      console.error('Error loading conditions:', err)
    }
  }

  async function loadLiveEvals() {
    try {
      const results: Record<string, LiveEval> = {}
      await Promise.all(symbols.map(async (s) => {
        const res = await fetch(`/api/v1/strategies/live/${s}`)
        if (res.ok) {
          results[s] = await res.json()
        }
      }))
      setLiveEvals(results)
    } catch (err) {
      console.error('Error loading live evals:', err)
    }
  }

  async function handleToggleRule(rule_code: string, enabled: boolean) {
    try {
      const payload = { enabled }
      await fetch(`/api/v1/strategies/rules/${rule_code}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      // Update local state for immediate feedback
      setRules(prev => prev.map(r => r.rule_code === rule_code ? { ...r, enabled } : r))
    } catch (err) {
      console.error('Error toggling rule:', err)
    }
  }

  const scalpingRules = rules.filter(r => r.strategy_type === 'scalping')
  const swingRules = rules.filter(r => r.strategy_type === 'swing')

  // Helper filter for directions
  const filteredScalping = scalpingRules.filter(r => r.direction === activeDir)
  const filteredSwing = swingRules.filter(r => r.direction === activeDir)

  return (
    <div className="strategies-page space-y-8 pb-20 p-8 min-h-screen">
      {/* HEADER */}
      <div className="flex justify-between items-center bg-[#0F172A]/50 p-6 rounded-2xl border border-white/5 backdrop-blur-xl">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-[0.65rem] font-black text-slate-500 uppercase tracking-widest">
            <Link href="/dashboard" className="hover:text-blue-400 transition-all">Dashboard</Link>
            <span>/</span>
            <span className="text-slate-300">Strategies</span>
          </div>
          <h1 className="text-3xl font-black italic tracking-tighter text-white">Strategy Engine <span className="text-blue-500">v1.0</span></h1>
        </div>
        
        <div className="flex items-center gap-6">
           <div className="text-right">
              <span className="text-[0.6rem] text-slate-500 uppercase font-black block leading-none mb-1 tracking-tighter">Active Rules</span>
              <span className="text-xl font-black text-emerald-500 italic uppercase">
                {rules.filter(r => r.enabled).length} / {rules.length}
              </span>
           </div>
           <div className="w-px h-10 bg-slate-800" />
           <div className="flex flex-col items-end">
              <span className="text-[0.6rem] text-slate-500 uppercase font-black block leading-none mb-1 tracking-tighter">Motor v2 Status</span>
              <span className="text-xs font-black text-blue-400 bg-blue-500/10 px-2 py-1 rounded">ACTIVE / STANDBY</span>
           </div>
        </div>
      </div>

      {/* TABS PRINCIPALES */}
      <div className="flex gap-4 p-2 bg-slate-900/50 rounded-2xl border border-white/5 w-fit">
        <button
          onClick={() => setActiveTab('scalping')}
          className={`px-8 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all flex items-center gap-3 ${
            activeTab === 'scalping' ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/30' : 'text-slate-500 hover:text-white hover:bg-white/5'
          }`}
        >
          <span>⚡ Scalping</span>
          <span className={`px-2 py-0.5 rounded-full text-[0.6rem] ${activeTab === 'scalping' ? 'bg-white/20' : 'bg-slate-800'}`}>
            {scalpingRules.length}
          </span>
        </button>
        <button
          onClick={() => setActiveTab('swing')}
          className={`px-8 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all flex items-center gap-3 ${
            activeTab === 'swing' ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30' : 'text-slate-500 hover:text-white hover:bg-white/5'
          }`}
        >
          <span>📈 Swing Trade</span>
          <span className={`px-2 py-0.5 rounded-full text-[0.6rem] ${activeTab === 'swing' ? 'bg-white/20' : 'bg-slate-800'}`}>
            {swingRules.length}
          </span>
        </button>
        <button
          onClick={() => setActiveTab('live')}
          className={`px-8 py-3 rounded-xl text-xs font-black uppercase tracking-widest transition-all flex items-center gap-3 ${
            activeTab === 'live' ? 'bg-emerald-600 text-white shadow-lg shadow-emerald-600/30' : 'text-slate-500 hover:text-white hover:bg-white/5'
          }`}
        >
          <span>🔴 Live Feed</span>
          <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
        </button>
      </div>

      {/* CONTENIDO POR TAB */}
      <div className="min-h-[400px]">
        {activeTab === 'scalping' && (
          <div className="space-y-6">
            <DirectionTabs activeDir={activeDir} setActiveDir={setActiveDir} />
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
               {filteredScalping.length > 0 ? (
                 filteredScalping.map(rule => (
                   <RuleCard key={rule.rule_code} rule={rule} onEdit={setEditingRule} onToggle={handleToggleRule} />
                 ))
               ) : (
                 <div className="col-span-full py-20 text-center text-slate-500 italic text-sm border-2 border-dashed border-slate-800 rounded-3xl">
                    No hay reglas de {activeDir} cargadas en Scalping.
                 </div>
               )}
            </div>
          </div>
        )}

        {activeTab === 'swing' && (
          <div className="space-y-6">
            <DirectionTabs activeDir={activeDir} setActiveDir={setActiveDir} />
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
              {filteredSwing.map(rule => (
                <RuleCard key={rule.rule_code} rule={rule} onEdit={setEditingRule} onToggle={handleToggleRule} />
              ))}
              {filteredSwing.length === 0 && (
                <div className="col-span-full py-20 text-center text-slate-500 italic text-sm border-2 border-dashed border-slate-800 rounded-3xl">
                   No hay reglas de {activeDir} cargadas en Swing Trade.
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'live' && (
          <LiveEvalPanel symbols={symbols} liveEvals={liveEvals} />
        )}
      </div>

      {/* EDIT MODAL */}
      {editingRule && (
        <EditRuleModal 
          rule={editingRule} 
          conditions={conditions} 
          onSave={() => { setEditingRule(null); loadRules(); }} 
          onClose={() => setEditingRule(null)} 
        />
      )}

      <style jsx global>{`
        body {
          background-color: #020617;
          color: #e2e8f0;
          font-family: 'Inter', sans-serif;
        }
        .strategies-page {
          background-color: #020617;
        }
        .neon-text {
          text-shadow: 0 0 10px rgba(16, 185, 129, 0.5);
        }
        .custom-scrollbar::-webkit-scrollbar {
          width: 8px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(0, 0, 0, 0.2);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
          background: rgba(255, 255, 255, 0.2);
        }
      `}</style>
    </div>
  )
}

function DirectionTabs({ activeDir, setActiveDir }: { activeDir: string, setActiveDir: (d: any) => void }) {
  return (
    <div className="flex gap-2">
      <button 
        onClick={() => setActiveDir('long')}
        className={`px-6 py-2 rounded-xl text-[0.65rem] font-black uppercase tracking-wider transition-all border ${
          activeDir === 'long' 
            ? `bg-emerald-500/10 text-emerald-500 border-emerald-500/50` 
            : 'bg-slate-900/50 text-slate-500 border-white/5 hover:border-white/10'
        }`}
      >
        Long Signals
      </button>
      <button 
        onClick={() => setActiveDir('short')}
        className={`px-6 py-2 rounded-xl text-[0.65rem] font-black uppercase tracking-wider transition-all border ${
          activeDir === 'short' 
            ? 'bg-rose-500/10 text-rose-500 border-rose-500/50' 
            : 'bg-slate-900/50 text-slate-500 border-white/5 hover:border-white/10'
        }`}
      >
        Short Signals
      </button>
    </div>
  )
}

const CycleBadges = ({ cycles }: { cycles: string[] }) => (
  <div className="flex gap-1.5 mt-1">
    {cycles.map(tf => {
      const colors = CYCLE_COLORS[tf] || { bg: '#222', text: '#AAA' }
      return (
        <span key={tf} style={{
          background: colors.bg,
          color: colors.text,
          border: `1px solid ${colors.text}44`,
          borderRadius: '4px',
          padding: '1px 6px',
          fontSize: '9px',
          fontWeight: 800,
          letterSpacing: '0.5px'
        }}>
          {tf.toUpperCase()}
        </span>
      )
    })}
  </div>
)

const RuleCard = ({ rule, onEdit, onToggle }: { 
  rule: StrategyRule, 
  onEdit: (r: StrategyRule) => void, 
  onToggle: (code: string, e: boolean) => void 
}) => {
  const dirColor = rule.direction === 'long' ? '#10b981' : '#f43f5e'
  const typeIcon = rule.strategy_type === 'scalping' ? '⚡' : '📈'
  const bgOpacity = rule.enabled ? 'bg-slate-900/40' : 'bg-slate-900/80 opacity-60'
  const applicableCycles = rule.applicable_cycles || [rule.cycle]

  return (
    <div 
      className={`relative group p-6 rounded-[2rem] border border-white/5 hover:border-white/10 transition-all duration-300 overflow-hidden ${bgOpacity}`}
      style={{ borderLeft: `4px solid ${dirColor}` }}
    >
      {/* Background Decor */}
      <div className="absolute top-0 right-0 p-4 opacity-[0.03] pointer-events-none">
        <span className="text-8xl font-black italic">{rule.rule_code}</span>
      </div>

      <div className="relative z-10 space-y-4">
        <div className="flex justify-between items-start">
          <div className="flex flex-col">
            <div className="flex items-center gap-2">
               <span className="text-xl font-black tracking-tighter" style={{ color: dirColor }}>
                 {typeIcon} {rule.rule_code}
               </span>
               <CycleBadges cycles={applicableCycles} />
            </div>
            <span className="text-[0.6rem] font-black text-slate-400 uppercase tracking-widest mt-1">
              {rule.direction} DIRECTION
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => onToggle(rule.rule_code, !rule.enabled)}
              className={`text-[0.6rem] font-black px-3 py-1.5 rounded-lg border transition-all ${
                rule.enabled 
                ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-500' 
                : 'bg-rose-500/10 border-rose-500/30 text-rose-500'
              }`}
            >
              {rule.enabled ? 'ACTIVE' : 'PAUSED'}
            </button>
            <button
              onClick={() => onEdit(rule)}
              className="p-1.5 bg-white/5 hover:bg-white/10 border border-white/5 rounded-lg transition-all"
              title="Edit Rule"
            >
              <span className="text-xs">✏️</span>
            </button>
          </div>
        </div>

        <div>
          <h4 className="text-sm font-black text-white italic leading-tight uppercase mb-1">{rule.name}</h4>
          <p className="text-[0.65rem] text-slate-500 line-clamp-2 italic">
            {rule.notes || "No hay notas adicionales para esta regla."}
          </p>
        </div>

        <div className="grid grid-cols-3 gap-2 py-4 border-y border-white/5">
           <div className="flex flex-col">
              <span className="text-[0.55rem] font-black text-slate-600 uppercase">Min Score</span>
              <span className="text-xs font-mono font-black text-white">{rule.min_score.toFixed(2)}</span>
           </div>
           <div className="flex flex-col">
              <span className="text-[0.55rem] font-black text-slate-600 uppercase">Avg Score</span>
              <span className="text-xs font-mono font-black text-white">{rule.score_promedio_24h?.toFixed(2) || '---'}</span>
           </div>
           <div className="flex flex-col">
              <span className="text-[0.55rem] font-black text-slate-600 uppercase">Hits 24h</span>
              <span className="text-xs font-mono font-black text-emerald-500">+{rule.activaciones_24h || 0}</span>
           </div>
        </div>

        {rule.score_promedio_24h > 0 && (
          <div className="pt-2">
            <div className="flex justify-between items-end mb-1.5">
               <span className="text-[0.55rem] font-black text-slate-600 uppercase">Engine Performance</span>
               <span className="text-[0.6rem] font-black text-white">{Math.round(rule.score_promedio_24h * 100)}%</span>
            </div>
            <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
               <div 
                 className="h-full transition-all duration-1000 rounded-full"
                 style={{ 
                   width: `${rule.score_promedio_24h * 100}%`,
                   backgroundColor: dirColor,
                   boxShadow: `0 0 10px ${dirColor}66`
                 }}
               />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function LiveEvalPanel({ symbols, liveEvals }: { symbols: string[], liveEvals: Record<string, LiveEval> }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {symbols.map(s => {
        const evalData = liveEvals[s]
        return (
          <div key={s} className="bg-[#0F172A]/80 border border-white/5 p-6 rounded-[2rem] space-y-6 relative overflow-hidden group">
            <div className="flex justify-between items-center">
              <h4 className="text-xl font-black italic tracking-tighter text-white">{s.replace('USDT','')}</h4>
              <div className="flex items-center gap-2">
                 <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                 <span className="text-[0.55rem] font-black text-emerald-500/80 uppercase">LIVE</span>
              </div>
            </div>

            {evalData?.best_opportunity ? (
              <div className="space-y-6">
                <div className="flex flex-col">
                  <span className="text-[0.55rem] text-slate-500 font-bold uppercase tracking-widest mb-1">BEST POTENTIAL RULE</span>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-black text-blue-400 bg-blue-500/10 px-2 py-0.5 rounded leading-none tabular-nums font-mono">
                      {evalData.best_opportunity.rule_code}
                    </span>
                    <span className={`text-base font-black italic ${evalData.best_opportunity.direction === 'long' ? 'text-emerald-500' : 'text-rose-500'}`}>
                      {evalData.best_opportunity.direction.toUpperCase()}
                    </span>
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="flex justify-between items-end">
                    <span className="text-[0.55rem] text-slate-500 font-bold uppercase tracking-widest">CURRENT MATCH</span>
                    <span className={`text-2xl font-black font-mono transition-all tabular-nums ${evalData.best_opportunity.triggered ? 'text-emerald-400 neon-text' : 'text-white'}`}>
                      {evalData.best_opportunity.score.toFixed(2)}
                    </span>
                  </div>
                  <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div 
                      className={`h-full transition-all duration-1000 ${evalData.best_opportunity.triggered ? 'bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.5)]' : 'bg-slate-600'}`} 
                      style={{ width: `${Math.min(evalData.best_opportunity.score * 100, 100)}%` }} 
                    />
                  </div>
                </div>

                <div className="space-y-4 pt-2">
                  <div className="space-y-1.5">
                    <span className="text-[0.5rem] font-black text-slate-600 uppercase tracking-[0.2em] block">PASSED FACTORS</span>
                    <div className="flex flex-wrap gap-1.5">
                      {evalData.best_opportunity.conditions_passed.map(c => (
                        <span key={c} className="text-[0.55rem] font-black text-emerald-400 bg-emerald-400/5 px-2 py-1 rounded border border-emerald-400/10">
                          {c}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <span className="text-[0.5rem] font-black text-slate-600 uppercase tracking-[0.2em] block">MISSING FACTORS</span>
                    <div className="flex flex-wrap gap-1.5">
                      {evalData.best_opportunity.conditions_failed.length > 0 ? (
                        evalData.best_opportunity.conditions_failed.map(c => (
                          <span key={c} className="text-[0.55rem] font-black text-rose-400/60 bg-rose-400/5 px-2 py-1 rounded border border-rose-400/10">
                            {c}
                          </span>
                        ))
                      ) : (
                        <span className="text-[0.6rem] text-emerald-400 font-black italic tracking-widest">TARGET ACQUIRED!</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="h-40 flex flex-col items-center justify-center text-slate-700 space-y-2 grayscale group-hover:grayscale-0 transition-all opacity-50">
                 <div className="text-4xl">📡</div>
                 <span className="text-[0.5rem] font-black uppercase tracking-[0.3em]">No Signal</span>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

const EditRuleModal = ({ rule, conditions, onSave, onClose }: { 
  rule: StrategyRule, 
  conditions: Condition[], 
  onSave: () => void, 
  onClose: () => void 
}) => {
  const [selectedCycles, setSelectedCycles] = useState<string[]>(rule.applicable_cycles || [rule.cycle] || ['15m'])
  const [form, setForm] = useState({
    name: rule.name,
    min_score: rule.min_score,
    condition_ids: rule.condition_ids || [],
    condition_weights: rule.condition_weights || {},
    enabled: rule.enabled,
    notes: rule.notes || '',
    confidence: rule.confidence || 'medium'
  })

  const [saving, setSaving] = useState(false)

  const toggleCycle = (tf: string) => {
    if (selectedCycles.includes(tf)) {
      if (selectedCycles.length > 1) {
        setSelectedCycles(selectedCycles.filter(c => c !== tf))
      }
    } else {
      setSelectedCycles([...selectedCycles, tf])
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const payload = {
        ...form,
        applicable_cycles: selectedCycles,
        cycle: selectedCycles[0] // Compatibilidad
      }
      await fetch(`/api/v1/strategies/rules/${rule.rule_code}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      onSave()
    } catch (err) {
      console.error('Error saving rule:', err)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 sm:p-12">
      <div 
        className="absolute inset-0 bg-slate-950/80 backdrop-blur-md" 
        onClick={onClose} 
      />
      <div className="relative w-full max-w-2xl bg-[#131B2E] border border-white/10 rounded-[2.5rem] shadow-2xl overflow-hidden animate-in fade-in zoom-in duration-300">
        <div className="p-8 sm:p-10 space-y-8 max-h-[85vh] overflow-y-auto custom-scrollbar">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[0.6rem] font-black text-blue-500 uppercase tracking-[0.3em] mb-2 block">Rule Configuration</span>
              <h2 className="text-3xl font-black italic text-white tracking-tighter">Edit Rule <span className="text-blue-500">_</span> {rule.rule_code}</h2>
            </div>
            <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-full text-slate-500 transition-colors">✕</button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
             <div className="space-y-4 col-span-full">
               <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block">Rule Name</label>
               <input 
                 value={form.name} 
                 onChange={e => setForm({...form, name: e.target.value})}
                 className="w-full bg-slate-900 border border-white/5 rounded-2xl px-5 py-4 text-sm font-bold text-white focus:border-blue-500 focus:outline-none transition-all"
               />
             </div>

             <div className="space-y-4">
               <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block">Minimum Activation Score</label>
               <input 
                 type="number" step="0.05" min="0" max="1"
                 value={form.min_score} 
                 onChange={e => setForm({...form, min_score: parseFloat(e.target.value)})}
                 className="w-full bg-slate-900 border border-white/5 rounded-2xl px-5 py-4 text-sm font-mono font-bold text-blue-400 focus:border-blue-500 focus:outline-none transition-all"
               />
             </div>

             <div className="space-y-4">
               <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block">Confidence Level</label>
               <select 
                 value={form.confidence}
                 onChange={e => setForm({...form, confidence: e.target.value})}
                 className="w-full bg-slate-900 border border-white/5 rounded-2xl px-5 py-4 text-sm font-bold text-white focus:border-blue-500 focus:outline-none transition-all"
               >
                 <option value="low">Low</option>
                 <option value="medium_low">Medium-Low</option>
                 <option value="medium">Medium</option>
                 <option value="medium_high">Medium-High</option>
                 <option value="high">High</option>
               </select>
             </div>
          </div>

          <div className="space-y-4">
            <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block">APPLICABLE TIMEFRAMES</label>
            <div className="flex gap-2">
              {AVAILABLE_CYCLES.map(tf => {
                const isSelected = selectedCycles.includes(tf)
                const colors = CYCLE_COLORS[tf]
                return (
                  <button
                    key={tf}
                    onClick={() => toggleCycle(tf)}
                    className={`px-6 py-2.5 rounded-xl text-xs font-bold transition-all border ${
                      isSelected 
                      ? 'shadow-lg shadow-black/20' 
                      : 'border-white/5 text-slate-500 hover:border-white/10'
                    }`}
                    style={{
                      background: isSelected ? colors.bg : 'transparent',
                      color: isSelected ? colors.text : undefined,
                      borderColor: isSelected ? `${colors.text}66` : undefined,
                    }}
                  >
                    {tf.toUpperCase()}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block">Condition Set & Weights</label>
              <span className="text-[0.6rem] font-black text-slate-600 bg-black/20 px-2 py-1 rounded">Sum: {Object.values(form.condition_weights).reduce((a, b: any) => a + (parseFloat(b) || 0), 0).toFixed(2)}</span>
            </div>

            <div className="space-y-3">
              {form.condition_ids.map(cid => {
                const cond = conditions.find(c => c.id === cid)
                const weight = form.condition_weights[cid] ?? (1 / (form.condition_ids.length || 1))
                return (
                  <div key={cid} className="flex items-center gap-4 bg-slate-900/50 p-4 rounded-2xl border border-white/5 hover:border-white/10 transition-all">
                    <div className="flex-1 flex flex-col">
                      <span className="text-[0.65rem] font-bold text-slate-300 mb-0.5">{cond?.name || `Condition #${cid}`}</span>
                      <span className="text-[0.55rem] font-black text-slate-500 uppercase font-mono">{cond?.variable?.source_field || 'System Variable'}</span>
                    </div>
                    <div className="w-20">
                       <input 
                         type="number" step="0.05" min="0" max="1"
                         value={weight}
                         onChange={e => setForm({
                           ...form,
                           condition_weights: { ...form.condition_weights, [cid]: parseFloat(e.target.value) }
                         })}
                         className="w-full bg-black/40 border border-white/5 rounded-xl px-2 py-2 text-xs font-mono font-bold text-center text-blue-400 focus:border-blue-400 focus:outline-none"
                       />
                    </div>
                    <button 
                      onClick={() => {
                        const newIds = form.condition_ids.filter(id => id !== cid)
                        const newWeights = { ...form.condition_weights }
                        delete newWeights[cid]
                        setForm({ ...form, condition_ids: newIds, condition_weights: newWeights })
                      }}
                      className="text-rose-500 hover:text-rose-400 p-2"
                    >
                      ✕
                    </button>
                  </div>
                )
              })}

              <div className="pt-2">
                <select 
                  onChange={e => {
                    const id = parseInt(e.target.value)
                    if (id && !form.condition_ids.includes(id)) {
                      setForm({
                        ...form,
                        condition_ids: [...form.condition_ids, id],
                        condition_weights: { ...form.condition_weights, [id]: 0.1 }
                      })
                    }
                  }}
                  className="w-full bg-white/5 border border-white/5 border-dashed rounded-2xl px-5 py-4 text-xs font-black text-blue-500 uppercase tracking-widest hover:bg-white/10 transition-all focus:outline-none cursor-pointer"
                >
                  <option value="">+ Add Processing Unit (Condition)</option>
                  {conditions.filter(c => !form.condition_ids.includes(c.id)).map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <label className="text-[0.6rem] font-black text-slate-500 uppercase tracking-widest block">Intelligence Notes</label>
            <textarea 
              rows={3}
              value={form.notes} 
              onChange={e => setForm({...form, notes: e.target.value})}
              placeholder="Analysis rationale, logic updates, or performance observations..."
              className="w-full bg-slate-900 border border-white/5 rounded-2xl px-5 py-4 text-sm font-medium text-slate-400 focus:border-blue-500 focus:outline-none transition-all resize-none"
            />
          </div>

          <div className="flex gap-4 pt-4">
            <button 
              onClick={onClose}
              className="flex-1 px-8 py-4 rounded-2xl text-xs font-black uppercase tracking-widest text-slate-500 hover:text-white hover:bg-white/5 transition-all"
            >
              Discard Changes
            </button>
            <button 
              onClick={handleSave}
              disabled={saving}
              className="flex-[2] bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-8 py-4 rounded-2xl text-xs font-black uppercase tracking-widest shadow-xl shadow-blue-600/20 transition-all flex items-center justify-center gap-2"
            >
              {saving ? 'Processing...' : 'Apply Logic Configuration'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
