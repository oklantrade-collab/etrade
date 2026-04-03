'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import toast from 'react-hot-toast'

interface ReadinessCriteria {
  met: boolean
  value: any
  required: any
}

interface ReadinessData {
  all_criteria_met: boolean
  criteria: {
    days_ok: ReadinessCriteria
    trades_ok: ReadinessCriteria
    win_rate_ok: ReadinessCriteria
    ev_ok: ReadinessCriteria
    no_excessive_losses: ReadinessCriteria
    drawdown_ok: ReadinessCriteria
  }
  pending: string[]
  evaluated_at: string
}

const CHECKLIST_ITEMS = [
  { id: 'api_keys', label: 'API keys de Binance REAL configuradas en Render', group: 'API Y SEGURIDAD' },
  { id: 'ip_whitelist', label: 'IP Whitelist en Binance apunta a IP de Frankfurt', group: 'API Y SEGURIDAD' },
  { id: 'permissions', label: 'Permisos Binance: Reading, Spot/Margin, Futures (NOT Withdrawals)', group: 'API Y SEGURIDAD' },
  { id: 'kill_switch', label: 'Kill switch probado — bot_active=False detiene el sistema', group: 'PROTECCIONES' },
  { id: 'circuit_breaker', label: 'Circuit breaker probado — se activa al 5% de pérdida', group: 'PROTECCIONES' },
  { id: 'reconciliation', label: 'Reconciliación probada — detecta discrepancias', group: 'PROTECCIONES' },
  { id: 'capital_def', label: 'Capital inicial definido', group: 'CAPITAL' },
  { id: 'capital_limit', label: 'Empezar con máximo 20% del capital real', group: 'CAPITAL' },
  { id: 'loss_calibrated', label: 'max_trade_loss_pct calibrado (1%)', group: 'CAPITAL' },
  { id: 'cb_calibrated', label: 'circuit_breaker_loss_pct calibrado (3-5%)', group: 'CAPITAL' },
  { id: 'telegram_p', label: 'Telegram recibe alertas de trades en tiempo real', group: 'MONITOREO' },
  { id: 'mobile_access', label: 'Dashboard accesible desde móvil', group: 'MONITOREO' },
  { id: 'runbook', label: 'Sé exactamente qué hacer si el sistema falla (runbook)', group: 'MONITOREO' },
]

export default function ReadinessPage() {
  const [readiness, setReadiness] = useState<ReadinessData | null>(null)
  const [checklist, setChecklist] = useState<Record<string, boolean>>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadReadiness()
    loadChecklist()
  }, [])

  async function loadReadiness() {
    try {
      const res = await fetch(`/api/v1/performance/real-mode-readiness`)
      if (res.ok) {
        setReadiness(await res.json())
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  async function loadChecklist() {
    try {
      const { data } = await supabase.from('trading_config').select('real_mode_checklist').eq('id', 1).single()
      if (data?.real_mode_checklist) {
        setChecklist(data.real_mode_checklist)
      }
    } catch (err) {
      console.error(err)
    }
  }

  async function toggleCheck(id: string) {
    const newVal = !checklist[id]
    const nextChecklist = { ...checklist, [id]: newVal }
    setChecklist(nextChecklist)
    
    // Auto-save to Supabase
    try {
      await supabase.from('trading_config').update({ real_mode_checklist: nextChecklist }).eq('id', 1)
    } catch (err) {
      console.error(err)
    }
  }

  const allChecklistDone = CHECKLIST_ITEMS.every(item => checklist[item.id])
  const canActivateReal = readiness?.all_criteria_met && allChecklistDone

  async function handleActivateReal() {
    if (!canActivateReal) return
    
    const confirmMsg = "⚠️ ATENCIÓN: Estás a punto de activar el modo real. Las próximas órdenes se ejecutarán con capital real en Binance. ¿Confirmar?"
    if (!window.confirm(confirmMsg)) return

    try {
      const { error } = await supabase.from('trading_config').update({ mode: 'real' }).eq('id', 1)
      if (!error) {
        toast.success('MODO REAL ACTIVADO. Sistema reiniciando el próximo ciclo.')
        window.location.href = '/dashboard'
      } else {
        toast.error('Error al activar modo real')
      }
    } catch (err) {
      toast.error('Excepción al activar modo real')
    }
  }

  if (loading) return <div className="p-20 text-center">Analizando criterios de performance...</div>

  return (
    <div className="space-y-8 pb-20">
      <div className="page-header">
        <h1 className="text-3xl font-black italic tracking-tighter">Real Mode Readiness</h1>
        <p className="text-xs text-slate-500 uppercase tracking-[0.2em] font-medium">Infrastructure & Performance Validation</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* SECCIÓN A — Performance Data */}
        <div className="card glass-effect space-y-6">
           <div className="flex justify-between items-center border-b border-slate-800 pb-4">
              <h2 className="text-lg font-bold text-slate-200">SECCIÓN A — Performance</h2>
              <span className={`px-3 py-1 rounded-full text-[10px] font-black tracking-widest ${readiness?.all_criteria_met ? 'bg-emerald-500/20 text-emerald-400' : 'bg-rose-500/20 text-rose-400'}`}>
                {readiness?.all_criteria_met ? 'CRITERIOS CUMPLIDOS' : 'PENDIENTE'}
              </span>
           </div>

           <div className="space-y-4">
              {readiness && Object.entries(readiness.criteria).map(([key, c]: [string, any]) => (
                <div key={key} className="flex items-center justify-between p-3 rounded-lg bg-slate-900/50 border border-slate-800">
                   <div className="flex items-center gap-3">
                      <span className="text-xl">{c.met ? '✅' : '🔴'}</span>
                      <span className="text-sm font-medium text-slate-300">
                        {key === 'days_ok' && '14 días de paper trading'}
                        {key === 'trades_ok' && '30 trades mínimos'}
                        {key === 'win_rate_ok' && 'Win rate >= 45%'}
                        {key === 'ev_ok' && 'EV global >= 0.10'}
                        {key === 'no_excessive_losses' && 'Sin > 4 pérdidas seguidas'}
                        {key === 'drawdown_ok' && 'Drawdown < 8%'}
                      </span>
                   </div>
                   <div className="text-right">
                      <span className="block text-xs font-bold text-white">{c.value}</span>
                      <span className="text-[10px] text-slate-500 uppercase">Req: {c.required}</span>
                   </div>
                </div>
              ))}
           </div>

           {!readiness?.all_criteria_met && (
              <div className="bg-amber-500/10 border border-amber-500/20 p-4 rounded-xl">
                 <p className="text-xs text-amber-500 leading-relaxed font-medium">
                   El sistema está acumulando datos en paper trading. Se requiere un historial consistente de al menos 14 días y 30 trades ganadores antes de habilitar el modo real.
                 </p>
              </div>
           )}
        </div>

        {/* SECCIÓN B — Infrastructure Checklist */}
        <div className="card glass-effect space-y-6">
           <div className="flex justify-between items-center border-b border-slate-800 pb-4">
              <h2 className="text-lg font-bold text-slate-200">SECCIÓN B — Infraestructura</h2>
              <span className={`px-3 py-1 rounded-full text-[10px] font-black tracking-widest ${allChecklistDone ? 'bg-emerald-500/20 text-emerald-400' : 'bg-blue-500/20 text-blue-400'}`}>
                {allChecklistDone ? 'CHECKLIST COMPLETO' : 'PENDIENTE'}
              </span>
           </div>

           <div className="space-y-6 overflow-y-auto max-h-[600px] pr-2 custom-scrollbar">
              {['API Y SEGURIDAD', 'PROTECCIONES', 'CAPITAL', 'MONITOREO'].map(group => (
                <div key={group} className="space-y-3">
                   <h3 className="text-[10px] font-black text-slate-500 uppercase tracking-widest">{group}</h3>
                   <div className="grid gap-2">
                      {CHECKLIST_ITEMS.filter(i => i.group === group).map(item => (
                        <div 
                          key={item.id}
                          onClick={() => toggleCheck(item.id)}
                          className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-all ${checklist[item.id] ? 'bg-emerald-500/5 border-emerald-500/20' : 'bg-slate-900/30 border-slate-800 hover:border-slate-700'}`}
                        >
                           <div className={`mt-0.5 w-4 h-4 rounded border flex items-center justify-center transition-colors ${checklist[item.id] ? 'bg-emerald-500 border-emerald-500' : 'bg-transparent border-slate-600'}`}>
                              {checklist[item.id] && <span className="text-[10px] text-white font-black">✓</span>}
                           </div>
                           <span className={`text-xs font-medium ${checklist[item.id] ? 'text-emerald-400' : 'text-slate-400'}`}>{item.label}</span>
                        </div>
                      ))}
                   </div>
                </div>
              ))}
           </div>
        </div>
      </div>

      <div className="flex flex-col items-center gap-6 pt-10">
         <div className="text-center space-y-2">
            <h3 className={`text-2xl font-black tracking-tighter italic ${canActivateReal ? 'text-emerald-500' : 'text-slate-600'}`}>
              ESTADO: {canActivateReal ? '✅ LISTO PARA MODO REAL' : '🔴 NO LISTO'}
            </h3>
            <p className="text-xs text-slate-500 uppercase font-bold tracking-widest">
              ({readiness?.pending.length || 0} / 6 performance criterias pending | {CHECKLIST_ITEMS.filter(i => !checklist[i.id]).length} checklist items pending)
            </p>
         </div>

         <button 
           disabled={!canActivateReal}
           onClick={handleActivateReal}
           className={`px-12 py-5 rounded-2xl font-black text-sm uppercase tracking-widest transition-all scale-100 hover:scale-105 active:scale-95 ${canActivateReal ? 'bg-emerald-600 text-white shadow-[0_0_30px_rgba(16,185,129,0.3)]' : 'bg-slate-900 text-slate-700 border border-slate-800 cursor-not-allowed'}`}
         >
           Activar Modo Real
         </button>
      </div>

      <style jsx>{`
        .glass-effect {
          background: rgba(26, 31, 46, 0.4);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: rgba(255, 255, 255, 0.02);
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: rgba(255, 255, 255, 0.1);
          border-radius: 2px;
        }
      `}</style>
    </div>
  )
}
