'use client'
import { useEffect, useState } from 'react'

type F = { key: string; label: string; unit?: string; kind?: 'num' | 'bool' | 'text' }
type Group = { id: string; title: string; open?: boolean; confirm?: boolean; fields: F[] }

const GROUPS: Group[] = [
  { id: 'A', title: 'A. Cuenta y riesgo', open: true, confirm: true, fields: [
    { key: 'capital_usd', label: 'Capital asignado (base)', unit: 'USD' },
    { key: 'max_risk_per_trade_usd', label: 'Riesgo máximo por operación', unit: 'USD' },
    { key: 'max_open_risk_usd', label: 'Riesgo abierto agregado máximo', unit: 'USD' },
    { key: 'daily_stop_usd', label: 'Stop diario de nuevas entradas', unit: 'USD' },
    { key: 'max_daily_selections', label: 'Máx. operaciones seleccionadas por día' },
    { key: 'max_open_positions', label: 'Máx. posiciones abiertas simultáneas' },
    { key: 'max_same_direction', label: 'Máx. posiciones en la misma dirección' },
    { key: 'commission_per_contract', label: 'Comisión por contrato', unit: 'USD' },
    { key: 'extra_fees_per_contract', label: 'Fees adicionales por contrato', unit: 'USD' },
  ]},
  { id: 'B', title: 'B. Universo y opcionabilidad', fields: [
    { key: 'max_underlyings', label: 'Máx. subyacentes analizados' },
    { key: 'min_underlying_price', label: 'Precio mínimo del subyacente', unit: 'USD' },
    { key: 'max_strike_gap_pct', label: 'Separación máx. entre strikes', unit: '%' },
    { key: 'min_atm_open_interest', label: 'Open interest mínimo ATM' },
    { key: 'pref_atm_volume', label: 'Volumen ATM preferido' },
    { key: 'max_atm_spread_pct', label: 'Spread relativo máx. ATM', unit: '%' },
    { key: 'block_events_in_dte', label: 'Bloquear earnings/catalizador dentro del DTE', kind: 'bool' },
    { key: 'iv_hv_expensive', label: 'IV/HV20 para marcar "prima cara"' },
    { key: 'supplementary_list_enabled', label: 'Lista complementaria de subyacentes líquidos (D-1)', kind: 'bool' },
    { key: 'supplementary_tickers', label: 'Tickers de la lista complementaria', kind: 'text' },
  ]},
  { id: 'C', title: 'C. Contratos y estrategias', fields: [
    { key: 'strat_long_call', label: 'Long Call', kind: 'bool' },
    { key: 'strat_long_put', label: 'Long Put', kind: 'bool' },
    { key: 'strat_bull_call_spread', label: 'Bull Call Spread', kind: 'bool' },
    { key: 'strat_bear_put_spread', label: 'Bear Put Spread', kind: 'bool' },
    { key: 'dte_min', label: 'DTE mínimo', unit: 'días' },
    { key: 'dte_max', label: 'DTE máximo', unit: 'días' },
    { key: 'delta_min', label: 'Delta mínimo pierna larga' },
    { key: 'delta_max', label: 'Delta máximo pierna larga' },
    { key: 'spread_width_min', label: 'Ancho mínimo de spread', unit: 'USD' },
    { key: 'spread_width_max', label: 'Ancho máximo de spread', unit: 'USD' },
    { key: 'max_leg_spread_pct', label: 'Spread relativo máx. por pierna', unit: '%' },
    { key: 'max_exec_overcost_pct', label: 'Sobrecoste de ejecución neto máx.', unit: '%' },
    { key: 'min_contract_oi', label: 'Open interest mínimo de contrato' },
    { key: 'min_contract_volume', label: 'Volumen mínimo de contrato' },
  ]},
  { id: 'D', title: 'D. Horario y datos', fields: [
    { key: 'entry_start_min_after_open', label: 'Inicio de entradas (min tras apertura)', unit: 'min' },
    { key: 'entry_end_min_before_close', label: 'Fin de entradas (min antes del cierre)', unit: 'min' },
    { key: 'force_close_min_before_close', label: 'Cierre forzado (min antes del cierre)', unit: 'min' },
    { key: 'scanner_freq_min', label: 'Frecuencia del scanner', unit: 'min' },
    { key: 'snapshot_freq_min', label: 'Frecuencia de snapshots', unit: 'min' },
    { key: 'snapshot_retention_days', label: 'Retención de snapshots', unit: 'días' },
    { key: 'max_quote_age_sec', label: 'Antigüedad máxima de cotización', unit: 's' },
    { key: 'allow_delayed_data', label: 'Permitir datos retrasados (gratuitos) — solo fase de prueba', kind: 'bool' },
    { key: 'max_concurrent_quotes', label: 'Máx. líneas de datos concurrentes' },
  ]},
  { id: 'E', title: 'E. Valoración y simulación', fields: [
    { key: 'alpha', label: 'alpha (fuerza del sesgo APEX)' },
    { key: 'vol_factor_k', label: 'Factor de volatilidad k sobre IV' },
    { key: 'slippage_normal', label: 'Slippage por pierna (normal)', unit: 'USD' },
    { key: 'slippage_adverse', label: 'Slippage por pierna (adverso)', unit: 'USD' },
    { key: 'exit_spread_mult_normal', label: 'Mult. spread de salida (normal)' },
    { key: 'exit_spread_mult_adverse', label: 'Mult. spread de salida (adverso)' },
    { key: 'min_ev_ratio', label: 'Ratio mínimo ev_view_net / max_loss' },
    { key: 'risk_free_rate_pct', label: 'Tasa libre de riesgo (respaldo)', unit: '%' },
  ]},
  { id: 'F', title: 'F. Options Score (pesos deben sumar 100)', fields: [
    { key: 'w_expectancy', label: 'Peso: expectativa neta', unit: '%' },
    { key: 'w_apex_signal', label: 'Peso: calidad de señal APEX', unit: '%' },
    { key: 'w_liquidity', label: 'Peso: liquidez y calidad de cotización', unit: '%' },
    { key: 'w_risk', label: 'Peso: riesgo y escenarios adversos', unit: '%' },
    { key: 'w_iv_greeks', label: 'Peso: IV y griegas', unit: '%' },
    { key: 'w_context', label: 'Peso: catalizadores y contexto', unit: '%' },
    { key: 'min_score', label: 'Score mínimo para ser elegible' },
    { key: 'ev_anchor', label: 'Ancla: ev/max_loss que vale 100' },
  ]},
  { id: 'G', title: 'G. Plan de salida', fields: [
    { key: 'long_tp_pct', label: 'Opción larga: take profit', unit: '% prima' },
    { key: 'long_sl_pct', label: 'Opción larga: stop', unit: '% prima' },
    { key: 'spread_tp_pct', label: 'Spread: take profit', unit: '% beneficio máx.' },
    { key: 'spread_sl_pct', label: 'Spread: stop', unit: '% débito' },
    { key: 'exit_on_direction_flip', label: 'Salir si la dirección APEX se invierte', kind: 'bool' },
  ]},
  { id: 'H', title: 'H. Gates (informativos)', fields: [
    { key: 'g1_min_sessions', label: 'G1: sesiones mínimas' },
    { key: 'g1_pct_sessions', label: 'G1: % de sesiones que deben cumplir', unit: '%' },
    { key: 'g1_min_optionable', label: 'G1: subyacentes optionables mínimos' },
    { key: 'g1_max_spread_pct', label: 'G1: spread relativo máx. candidata viable', unit: '%' },
    { key: 'g1_max_risk_usd', label: 'G1: riesgo máx. candidata viable', unit: 'USD' },
    { key: 'g3_min_weeks', label: 'G3: semanas mínimas en shadow' },
    { key: 'g3_min_trades', label: 'G3: operaciones simuladas mínimas' },
    { key: 'g3_calibration_tol_pts', label: 'G3: tolerancia de calibración', unit: 'pts' },
  ]},
]

export default function OptionsSettings() {
  const [data, setData] = useState<any>(null)
  const [vals, setVals] = useState<Record<string, any>>({})
  const [open, setOpen] = useState<Record<string, boolean>>({ A: true })
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  const load = () => fetch('/api/v1/options/settings').then(r => r.json()).then(d => { setData(d); setVals(d.settings) })
    .catch(() => setMsg({ ok: false, text: 'No se pudo cargar la configuración de Opciones' }))
  useEffect(() => { load() }, [])

  const set = (k: string, v: any) => setVals(p => ({ ...p, [k]: v }))
  const resetGroup = (g: Group) => g.fields.forEach(f => set(f.key, data.defaults[f.key]))

  const save = async () => {
    const changedA = GROUPS[0].fields.some(f => String(vals[f.key]) !== String(data.settings[f.key]))
    if (changedA && !confirm('Está cambiando parámetros de Cuenta y riesgo. Aplican solo a nuevas candidatas y entradas. ¿Confirmar?')) return
    setSaving(true); setMsg(null)
    const res = await fetch('/api/v1/options/settings', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values: vals }),
    })
    const body = await res.json().catch(() => ({}))
    if (res.ok) { setMsg({ ok: true, text: `Guardado (versión ${body.settings_version})` }); load() }
    else setMsg({ ok: false, text: Array.isArray(body.detail) ? body.detail.join(' · ') : (body.detail || `Error ${res.status}`) })
    setSaving(false)
  }

  if (!data) return <div style={{ color: '#666', padding: 20 }}>Cargando…</div>
  const eff = data.effective
  const inp: React.CSSProperties = { width: 140, padding: '6px 10px', borderRadius: 6, background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 13 }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 900 }}>
      <div style={{ padding: 20, borderRadius: 14, background: 'rgba(17,24,39,0.5)', border: '1px solid rgba(255,255,255,0.05)', display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <b style={{ color: '#FFF' }}>Options APEX · Paper Trading</b>
        <span style={{ padding: '3px 10px', borderRadius: 10, border: '1px solid #26A69A', color: '#26A69A', fontSize: 11, fontWeight: 900 }}>PAPER (bloqueado)</span>
        <span style={{ color: '#777', fontSize: 12 }}>
          Techos de entorno: ${data.hard_caps.max_risk_per_trade_usd}/operación · ${data.hard_caps.max_open_risk_usd} abierto · {data.hard_caps.max_daily_selections} selecciones/día.
          Activación del módulo: variables <code>OPTIONS_ENABLED</code> / <code>NEXT_PUBLIC_OPTIONS_ENABLED</code>.
        </span>
      </div>
      {data.storage_error && (
        <div style={{ color: '#FFA726', fontSize: 12 }}>Tablas opt_* no disponibles: se muestran valores por defecto. Ejecute <code>backend/sql/opt_001_foundation.sql</code>.</div>
      )}

      {GROUPS.map(g => (
        <div key={g.id} style={{ borderRadius: 14, background: 'rgba(17,24,39,0.4)', border: '1px solid rgba(255,255,255,0.05)' }}>
          <button onClick={() => setOpen(p => ({ ...p, [g.id]: !p[g.id] }))} style={{ width: '100%', textAlign: 'left', padding: '14px 20px', background: 'transparent', border: 'none', color: '#DDD', fontWeight: 700, fontSize: 14, cursor: 'pointer' }}>
            {open[g.id] ? '▾' : '▸'} {g.title}
          </button>
          {open[g.id] && (
            <div style={{ padding: '0 20px 16px' }}>
              {g.fields.map(f => {
                const range = data.ranges[f.key]
                const clipped = !['bool', 'text'].includes(f.kind || '') && eff[f.key] !== undefined && Number(eff[f.key]) !== Number(vals[f.key]) && typeof eff[f.key] === 'number'
                return (
                  <div key={f.key} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0', borderTop: '1px solid rgba(255,255,255,0.03)' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ color: '#CCC', fontSize: 13 }}>{f.label}</div>
                      <div style={{ color: clipped ? '#FFA726' : '#555', fontSize: 11 }}>
                        {range && range.min !== null ? `Rango ${range.min}–${range.max}. ` : ''}Defecto: {String(data.defaults[f.key])}.
                        {clipped ? ` Efectivo: ${eff[f.key]} (recortado por techo)` : ''}
                      </div>
                    </div>
                    {f.kind === 'bool' ? (
                      <input type="checkbox" checked={!!vals[f.key]} onChange={e => set(f.key, e.target.checked)} />
                    ) : f.kind === 'text' ? (
                      <input style={inp} value={vals[f.key] ?? ''} onChange={e => set(f.key, e.target.value)} />
                    ) : (
                      <input style={inp} type="number" step="any" value={vals[f.key] ?? ''} onChange={e => set(f.key, e.target.value === '' ? '' : Number(e.target.value))} />
                    )}
                    <span style={{ width: 60, color: '#555', fontSize: 11 }}>{f.unit}</span>
                  </div>
                )
              })}
              <button onClick={() => resetGroup(g)} style={{ marginTop: 8, padding: '6px 12px', fontSize: 11, color: '#999', background: 'transparent', border: '1px solid #333', borderRadius: 6, cursor: 'pointer' }}>
                Restaurar valores por defecto
              </button>
            </div>
          )}
        </div>
      ))}

      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <button onClick={save} disabled={saving} style={{ padding: '10px 28px', borderRadius: 8, background: '#AB47BC', color: '#FFF', fontWeight: 700, border: 'none', cursor: 'pointer' }}>
          {saving ? 'Guardando…' : 'Guardar configuración de Opciones'}
        </button>
        {msg && <span style={{ color: msg.ok ? '#26A69A' : '#EF5350', fontSize: 13 }}>{msg.text}</span>}
        <span style={{ marginLeft: 'auto', color: '#555', fontSize: 11 }}>settings_version: {data.settings_version}</span>
      </div>
    </div>
  )
}
