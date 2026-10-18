'use client'
import { useCallback, useEffect, useState } from 'react'
import { optCard } from './OptionsShell'

export default function UniverseCard() {
  const [uni, setUni] = useState<any>(null)
  const [job, setJob] = useState<any>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [openSym, setOpenSym] = useState<string | null>(null)
  const [chain, setChain] = useState<any>(null)

  const load = useCallback(() => {
    fetch('/api/v1/options/universe').then(r => r.ok ? r.json() : null).then(setUni).catch(() => {})
    fetch('/api/v1/options/jobs?limit=1').then(r => r.ok ? r.json() : null).then(d => setJob(d?.items?.[0] ?? null)).catch(() => {})
  }, [])
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t) }, [load])

  const scan = async () => {
    setMsg(null)
    const r = await fetch('/api/v1/options/jobs/scan', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    const b = await r.json().catch(() => ({}))
    setMsg(r.ok ? `Scan encolado (job ${b.job_id}). El Options Worker lo ejecutará.` : (b.detail || `Error ${r.status}`))
    load()
  }
  const showChain = async (sym: string) => {
    if (openSym === sym) { setOpenSym(null); return }
    setOpenSym(sym); setChain(null)
    const r = await fetch(`/api/v1/options/chains/${sym}`)
    setChain(r.ok ? await r.json() : { contracts: [] })
  }

  const th: React.CSSProperties = { textAlign: 'left', color: '#555', fontSize: 10, textTransform: 'uppercase', padding: '6px 10px' }
  const td: React.CSSProperties = { color: '#AAA', fontSize: 12, padding: '6px 10px', borderTop: '1px solid rgba(255,255,255,0.04)' }
  const n = (v: any, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))

  return (
    <div style={optCard}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ fontSize: 10, fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.2em' }}>
          Universo APEX · opcionabilidad ({uni ? `${uni.optionable} optionables / ${uni.rejected} descartados` : '…'})
        </div>
        <button onClick={scan} style={{ marginLeft: 'auto', padding: '6px 14px', borderRadius: 8, background: '#AB47BC', color: '#FFF', border: 'none', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}>
          Ejecutar scan
        </button>
      </div>
      {msg && <div style={{ color: '#FFA726', fontSize: 12, marginBottom: 8 }}>{msg}</div>}
      {job && <div style={{ color: '#666', fontSize: 11, marginBottom: 8 }}>Último job #{job.id} ({job.type}): <b style={{ color: job.status === 'error' ? '#EF5350' : '#AAA' }}>{job.status}</b>{job.error ? ` — ${job.error}` : ''}</div>}
      {uni?.items?.length === 0 && <div style={{ color: '#666', fontSize: 13 }}>Sin datos todavía. Inicie el Options Worker (<code>run_options_worker.bat</code>) con TWS paper abierto y pulse “Ejecutar scan”.</div>}
      {uni?.items?.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead><tr><th style={th}>Ticker</th><th style={th}>APEX</th><th style={th}>Precio</th><th style={th}>Spread ATM %</th><th style={th}>OI ATM</th><th style={th}>Datos</th><th style={th}>Estado</th><th style={th}>Motivo / avisos</th></tr></thead>
          <tbody>{uni.items.map((u: any) => (
            <>
              <tr key={u.symbol} style={{ cursor: u.optionable ? 'pointer' : 'default' }} onClick={() => u.optionable && showChain(u.symbol)}>
                <td style={{ ...td, color: '#FFF', fontWeight: 700 }}>{u.symbol}</td>
                <td style={td}>{n(u.apex_score, 1)}</td><td style={td}>{n(u.price)}</td>
                <td style={td}>{n(u.atm_spread_pct, 1)}</td><td style={td}>{n(u.atm_oi, 0)}</td>
                <td style={td}>{u.data_state ?? '—'}</td>
                <td style={{ ...td, color: u.optionable ? '#26A69A' : '#EF5350' }}>{u.optionable ? 'OPTIONABLE' : 'DESCARTADO'}</td>
                <td style={{ ...td, color: '#777' }}>{u.optionable_reason || (u.warnings || []).join(' · ') || ''}</td>
              </tr>
              {openSym === u.symbol && (
                <tr key={u.symbol + '-c'}><td colSpan={8} style={{ ...td, background: 'rgba(255,255,255,0.02)' }}>
                  {!chain ? 'Cargando cadena…' : chain.contracts.length === 0 ? 'Sin contratos guardados.' : (
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                      <thead><tr><th style={th}>Venc.</th><th style={th}>Tipo</th><th style={th}>Strike</th><th style={th}>Bid</th><th style={th}>Ask</th><th style={th}>IV</th><th style={th}>Delta</th><th style={th}>Dato</th><th style={th}>Usable</th></tr></thead>
                      <tbody>{chain.contracts.map((c: any) => { const q = c.opt_quotes_latest || {}; return (
                        <tr key={c.id}><td style={td}>{c.expiry}</td><td style={td}>{c.right}</td><td style={td}>{n(c.strike)}</td>
                          <td style={td}>{n(q.bid)}</td><td style={td}>{n(q.ask)}</td><td style={td}>{n(q.iv, 3)}</td><td style={td}>{n(q.delta, 3)}</td>
                          <td style={td}>{q.market_data_type ?? '—'}</td><td style={{ ...td, color: q.usable ? '#26A69A' : '#EF5350' }}>{q.usable ? 'sí' : (q.unusable_reason || 'no')}</td></tr>) })}</tbody>
                    </table>
                  )}
                </td></tr>
              )}
            </>
          ))}</tbody>
        </table>
      )}
    </div>
  )
}
