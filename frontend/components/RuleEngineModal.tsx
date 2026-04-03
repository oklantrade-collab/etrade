'use client'
import React, { useState, useEffect } from 'react'
import { supabase } from '@/lib/supabase'

interface Rule {
  id: number
  rule_code: string
  name: string
  description: string
  direction: string
  enabled: boolean
  priority: number
  confidence: string
  conditions: any[]
  logic: string
}

export default function RuleEngineModal({ isOpen, onClose }: { isOpen: boolean, onClose: () => void }) {
  const [rules, setRules] = useState<Rule[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (isOpen) {
      fetchRules()
    }
  }, [isOpen])

  async function fetchRules() {
    setLoading(true)
    const { data } = await supabase.from('trading_rules').select('*').order('priority')
    if (data) setRules(data)
    setLoading(false)
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
      <div className="bg-[#1a1f2e] border border-slate-800 w-full max-w-4xl max-h-[90vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-800 flex justify-between items-center">
          <div>
            <h2 className="text-xl font-bold">Rule Engine</h2>
            <p className="text-xs text-slate-500 uppercase tracking-widest mt-1">Configure Entry & Exit Logic (Aa/Bb)</p>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-slate-800 rounded-full transition-colors">
            <span className="text-xl">✕</span>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {loading ? (
            <div className="py-20 text-center text-slate-500">Loading rules...</div>
          ) : (
            rules.map((rule) => (
              <div key={rule.id} className={`p-4 rounded-xl border ${rule.enabled ? 'border-slate-800 bg-slate-900/40' : 'border-dashed border-slate-800 opacity-60'}`}>
                <div className="flex justify-between items-start">
                  <div className="flex items-center gap-3">
                    <span className={`px-2 py-0.5 rounded text-[0.65rem] font-bold ${rule.direction === 'long' ? 'bg-emerald-500/20 text-emerald-500' : 'bg-rose-500/20 text-rose-500'}`}>
                      {rule.rule_code}
                    </span>
                    <h3 className="font-semibold">{rule.name}</h3>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="flex flex-col items-end">
                      <span className="text-[0.65rem] text-slate-500 uppercase">Priority</span>
                      <span className="text-xs font-mono">{rule.priority}</span>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer">
                      <input type="checkbox" checked={rule.enabled} readOnly className="sr-only peer" />
                      <div className="w-9 h-5 bg-slate-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600"></div>
                    </label>
                  </div>
                </div>
                
                <p className="text-sm text-slate-400 mt-2">{rule.description}</p>
                
                <div className="mt-4 flex gap-2 flex-wrap">
                  {rule.conditions?.map((cond: any, idx: number) => (
                    <div key={idx} className="bg-slate-800/50 px-2 py-1 rounded border border-slate-700 text-[0.7rem] font-mono">
                      <span className="text-blue-400">{cond.indicator}</span> <span className="text-slate-500">{cond.operator}</span> <span className="text-amber-400">{cond.value}</span>
                    </div>
                  ))}
                  <div className="px-2 py-1 text-[0.7rem] font-bold text-slate-500">LOGIC: {rule.logic}</div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/40 flex justify-between items-center">
          <span className="text-xs text-slate-500 italic">Total Rules: {rules.length} ({rules.filter(r => r.enabled).length} active)</span>
          <div className="flex gap-3">
            <button className="btn btn-ghost !py-1.5 !px-4 text-sm" disabled>View History</button>
            <button className="btn btn-primary !py-1.5 !px-6 text-sm">Save Changes</button>
          </div>
        </div>
      </div>
    </div>
  )
}
