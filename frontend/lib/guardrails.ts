// frontend/lib/guardrails.ts
import { supabase } from './supabase'

export interface ParameterBound {
  parameter_name: string
  category: string
  min_value: number
  max_value: number
  default_value: number
  current_value: number
  description: string
  unit: string
  regime: string
  last_changed_at: string
  last_changed_by: string
  change_reason: string
  perf_ev_after?: number
}

export interface ParameterChangeLog {
  id: number
  parameter_name: string
  old_value: number
  new_value: number
  changed_at: string
  changed_by: string
  change_reason: string
  within_bounds: boolean
  accepted: boolean
  backtest_ev?: number
}

export async function getParameterBounds() {
  const { data, error } = await supabase
    .from('parameter_bounds')
    .select('*')
    .order('category', { ascending: true })
  
  if (error) throw error
  return data as ParameterBound[]
}

export async function getParameterHistory(limit = 10) {
  const { data, error } = await supabase
    .from('parameter_changes_log')
    .select('*')
    .order('changed_at', { ascending: false })
    .limit(limit)
  
  if (error) throw error
  return data as ParameterChangeLog[]
}

export async function updateParameterValue(
  name: string, 
  value: number, 
  reason: string,
  backtestResult?: { win_rate: number; avg_rr: number; total_trades: number }
) {
  const response = await fetch(`/api/v1/risk/validate-param`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      parameter_name: name,
      new_value: value,
      changed_by: 'jhon', // UI defaults to user
      change_reason: reason,
      backtest_result: backtestResult
    })
  })
  
  const result = await response.json()
  
  if (!response.ok || !result.accepted) {
    throw new Error(result.reason || 'Validation failed')
  }
  
  return result
}
