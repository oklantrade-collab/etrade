// frontend/components/GuardrailControl.tsx
'use client'
import { useState, useEffect } from 'react'
import { ParameterBound, updateParameterValue } from '@/lib/guardrails'
import { toast } from 'react-hot-toast'

interface Props {
  bound: ParameterBound
  onUpdate: () => void
}

export default function GuardrailControl({ bound, onUpdate }: Props) {
  const [value, setValue] = useState(bound.current_value)
  const [reason, setReason] = useState('')
  const [isUpdating, setIsUpdating] = useState(false)
  const [hasChanged, setHasChanged] = useState(false)

  useEffect(() => {
    setValue(bound.current_value)
    setHasChanged(false)
  }, [bound.current_value])

  const handleUpdate = async () => {
    if (!reason) {
      toast.error('Indique un motivo para el cambio')
      return
    }

    setIsUpdating(true)
    try {
      await updateParameterValue(bound.parameter_name, value, reason)
      toast.success('Parámetro actualizado')
      setReason('')
      setHasChanged(false)
      onUpdate()
    } catch (error: any) {
      toast.error(`Error: ${error.message}`)
    } finally {
      setIsUpdating(false)
    }
  }

  const isWithin = value >= bound.min_value && value <= bound.max_value
  const labels: Record<string, string> = {
    'alto_riesgo': '🔴 Alto',
    'riesgo_medio': '🟡 Medio',
    'bajo_riesgo': '🟢 Bajo',
    'all': '⚪ Global'
  }

  return (
    <div className="p-4 bg-slate-900/40 rounded-xl border border-slate-800 space-y-4 hover:border-slate-700 transition-all">
      <div className="flex justify-between items-start">
        <div>
          <h4 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            {bound.parameter_name}
            <span className="px-2 py-0.5 bg-slate-800 rounded text-[9px] font-black uppercase text-slate-500 tracking-tighter">
              {labels[bound.regime] || bound.regime}
            </span>
          </h4>
          <p className="text-[10px] text-slate-500 mt-1 max-w-xs leading-tight">
            {bound.description}
          </p>
        </div>
        <div className="text-right">
           <span className={`text-xl font-black italic tracking-tighter ${hasChanged ? 'text-blue-400' : 'text-slate-300'}`}>
             {value}
           </span>
           <span className="block text-[9px] text-slate-600 font-bold uppercase">{bound.unit}</span>
        </div>
      </div>

      <div className="space-y-2">
        <input 
          type="range"
          min={bound.min_value}
          max={bound.max_value}
          step={bound.unit === 'pct' ? 0.5 : 0.05}
          value={value}
          onChange={(e) => {
            setValue(Number(e.target.value))
            setHasChanged(true)
          }}
          className={`w-full h-1.5 rounded-lg appearance-none cursor-pointer transition-all ${
            isWithin ? 'bg-slate-700 accent-blue-500' : 'bg-rose-900/40 accent-rose-500'
          }`}
        />
        <div className="flex justify-between text-[10px] uppercase font-black tracking-widest text-slate-600">
          <span>Min {bound.min_value}</span>
          <span>{isWithin ? '✅ EN BOUNDS' : '⚠️ FUERA DE BOUNDS'}</span>
          <span>Max {bound.max_value}</span>
        </div>
      </div>

      {hasChanged && (
        <div className="pt-2 animate-in fade-in slide-in-from-top-2 duration-300">
           <div className="flex gap-2">
             <input 
               type="text" 
               placeholder="Motivo del ajuste..." 
               className="bg-slate-950/50 border border-slate-800 rounded px-3 py-1.5 text-xs flex-1 outline-none focus:border-blue-500/50"
               value={reason}
               onChange={(e) => setReason(e.target.value)}
             />
             <button 
               onClick={handleUpdate}
               disabled={isUpdating}
               className="bg-blue-600 hover:bg-blue-500 text-white rounded px-4 py-1.5 text-xs font-bold uppercase transition-colors"
             >
               {isUpdating ? '...' : 'APLICAR'}
             </button>
             <button 
               onClick={() => { setValue(bound.current_value); setHasChanged(false); }}
               className="text-slate-500 hover:text-slate-300 text-xs px-2"
             >
               CANCEL
             </button>
           </div>
        </div>
      )}
    </div>
  )
}
