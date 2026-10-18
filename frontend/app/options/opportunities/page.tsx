'use client'
import { Fragment, useEffect, useState } from 'react'
import Link from 'next/link'
import { OptionsShell, optCard } from '@/components/options/OptionsShell'

const STRAT: Record<string, string> = {
  long_call: 'Long Call',
  long_put: 'Long Put',
  bull_call_spread: 'Bull Call Spread',
  bear_put_spread: 'Bear Put Spread',
}

const n = (v: any, d = 2) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))

function ScoreBadge({ score }: { score: number | null | undefined }) {
  if (score === null || score === undefined) return <span style={{ color: '#666' }}>—</span>
  const sc = Number(score)
  let bg = 'rgba(239, 83, 80, 0.15)', color = '#EF5350'
  if (sc >= 75) {
    bg = 'rgba(34, 197, 94, 0.2)'
    color = '#22C55E'
  } else if (sc >= 60) {
    bg = 'rgba(56, 189, 248, 0.2)'
    color = '#38BDF8'
  } else if (sc >= 45) {
    bg = 'rgba(255, 167, 38, 0.2)'
    color = '#FFA726'
  }
  return (
    <span style={{
      display: 'inline-block',
      padding: '3px 8px',
      borderRadius: 6,
      background: bg,
      color,
      fontWeight: 800,
      fontSize: 11,
      minWidth: 34,
      textAlign: 'center',
      border: `1px solid ${color}33`,
    }}>
      {sc.toFixed(1)}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'selected') {
    return (
      <span style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '3px 9px',
        borderRadius: 6,
        background: 'rgba(255, 215, 0, 0.2)',
        color: '#FFD700',
        fontWeight: 800,
        fontSize: 10,
        textTransform: 'uppercase',
        border: '1px solid rgba(255, 215, 0, 0.4)',
      }}>
        ★ Seleccionada
      </span>
    )
  }
  if (status === 'eligible') {
    return (
      <span style={{
        display: 'inline-block',
        padding: '3px 8px',
        borderRadius: 6,
        background: 'rgba(34, 197, 94, 0.15)',
        color: '#22C55E',
        fontWeight: 700,
        fontSize: 10,
        textTransform: 'uppercase',
        border: '1px solid rgba(34, 197, 94, 0.3)',
      }}>
        Elegible
      </span>
    )
  }
  if (status === 'rejected') {
    return (
      <span style={{
        display: 'inline-block',
        padding: '3px 8px',
        borderRadius: 6,
        background: 'rgba(239, 83, 80, 0.12)',
        color: '#EF5350',
        fontSize: 10,
        textTransform: 'uppercase',
        border: '1px solid rgba(239, 83, 80, 0.25)',
      }}>
        Descartada
      </span>
    )
  }
  return <span style={{ color: '#888', fontSize: 10 }}>{status}</span>
}

function CatalystSemaphores({ meta }: { meta?: any }) {
  const c1 = Boolean(meta?.c1_gap?.confirmed || meta?.c1_gap?.triggered)
  const c2 = Boolean(meta?.c2_basis_1h?.triggered || meta?.c2_basis_1h?.type)
  const c3 = Boolean(meta?.c3_adx?.triggered || (meta?.c3_adx?.adx ?? 0) >= 20)
  const c4 = Boolean(meta?.c4_rebote?.triggered || meta?.c4_rebote?.rule_code)

  const pill = (label: string, ok: boolean, color = '#22C55E') => (
    <span style={{
      fontSize: 9,
      fontWeight: 800,
      padding: '2px 6px',
      borderRadius: 4,
      background: ok ? `${color}22` : 'rgba(255,255,255,0.04)',
      color: ok ? color : '#666',
      border: `1px solid ${ok ? color + '44' : 'rgba(255,255,255,0.06)'}`,
      display: 'inline-flex',
      alignItems: 'center',
      gap: 3,
    }}>
      <span style={{ fontSize: 7 }}>{ok ? '●' : '○'}</span>
      {label}
    </span>
  )

  return (
    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
      {pill('C1 GAP', c1, '#38BDF8')}
      {pill('C2 BASIS', c2, '#22C55E')}
      {pill('C3 ADX', c3, '#FFA726')}
      {pill('C4 REBOTE', c4, '#AB47BC')}
    </div>
  )
}

function Payoff({ data, be }: { data: { price: number; pnl: number }[]; be: number | null }) {
  if (!data?.length) return <div style={{ color: '#666', fontSize: 12 }}>Sin curva (faltan datos).</div>
  const W = 420, H = 140, P = 24
  const xs = data.map(d => d.price), ys = data.map(d => d.pnl)
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys, 0), y1 = Math.max(...ys, 0)
  const dx = x1 - x0 || 1, dy = y1 - y0 || 1
  const mapX = (x: number) => P + ((x - x0) / dx) * (W - 2 * P)
  const mapY = (y: number) => H - P - ((y - y0) / dy) * (H - 2 * P)
  const pts = data.map(d => `${mapX(d.price).toFixed(1)},${mapY(d.pnl).toFixed(1)}`).join(' ')
  const yZero = mapY(0)
  const beX = be != null && be >= x0 && be <= x1 ? mapX(be) : null

  return (
    <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: 8, padding: 12, border: '1px solid rgba(255,255,255,0.06)' }}>
      <div style={{ fontSize: 11, color: '#888', marginBottom: 6, display: 'flex', justifyContent: 'space-between' }}>
        <span>Curva de Payoff al Vencimiento</span>
        {be != null && <span style={{ color: '#FFD700' }}>BE: ${be.toFixed(2)}</span>}
      </div>
      <svg width={W} height={H} style={{ overflow: 'visible' }}>
        <line x1={P} y1={yZero} x2={W - P} y2={yZero} stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" />
        {beX != null && <line x1={beX} y1={P} x2={beX} y2={H - P} stroke="rgba(255,215,0,0.4)" strokeDasharray="2 2" />}
        <polyline fill="none" stroke="#22C55E" strokeWidth="2" points={pts} />
      </svg>
    </div>
  )
}

export default function OpportunitiesPage() {
  const [data, setData] = useState<{ items: any[]; summary: any } | null>(null)
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [status, setStatus] = useState<string>('all')
  const [direction, setDirection] = useState<string>('all')
  const [strategy, setStrategy] = useState<string>('')
  const [search, setSearch] = useState<string>('')
  const [sel, setSel] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [runningSelect, setRunningSelect] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [simulating, setSimulating] = useState(false)

  const loadData = async () => {
    setLoading(true)
    setErr(null)
    const p = new URLSearchParams()
    if (status !== 'all') p.set('status', status)
    if (direction !== 'all') p.set('direction', direction)
    if (strategy) p.set('strategy', strategy)
    if (search) p.set('symbol', search)

    try {
      const res = await fetch(`/api/v1/options/opportunities?${p.toString()}`).then(r => r.json())
      setData(res)
    } catch {
      setErr('Error de red al conectar con la API de Opportunities')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [status, direction, strategy])

  const openDetail = async (id: number) => {
    if (sel === id) {
      setSel(null)
      setDetail(null)
      return
    }
    setSel(id)
    setDetail(null)
    try {
      const res = await fetch(`/api/v1/options/candidates/${id}`).then(r => r.json())
      setDetail(res)
    } catch {
      setDetail(null)
    }
  }

  const triggerPortfolio = async () => {
    setRunningSelect(true)
    try {
      await fetch('/api/v1/options/portfolio/select', { method: 'POST' })
      await loadData()
      setMsg('Cartera re-evaluada con éxito.')
    } catch {
      setErr('Error al ejecutar el selector de cartera')
    } finally {
      setRunningSelect(false)
    }
  }

  const triggerCatalystScan = async () => {
    setScanning(true)
    setMsg(null)
    setErr(null)
    try {
      const res = await fetch('/api/v1/options/catalysts/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      }).then(r => r.json())
      setMsg(`¡Escaneo de catalizadores completado! ${res.calls_selected ?? 0} CALLs y ${res.puts_selected ?? 0} PUTs actualizadas.`)
      await loadData()
    } catch {
      setErr('Error al ejecutar escaneo de catalizadores')
    } finally {
      setScanning(false)
    }
  }

  const handleSimulateEntry = async (cid: number) => {
    setSimulating(true)
    setErr(null)
    setMsg(null)
    try {
      const res = await fetch('/api/v1/options/positions/simulate-entry', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate_id: cid }),
      }).then(r => r.json())
      if (res.ok) {
        setMsg(`¡Posición Paper abierta exitosamente para ${res.position?.symbol}! Ver en "Positions".`)
        await loadData()
      } else {
        setErr(res.detail || 'Error al simular entrada')
      }
    } catch {
      setErr('Error de red al conectar con la API')
    } finally {
      setSimulating(false)
    }
  }

  const summary = data?.summary
  const items = data?.items || []
  const topCalls = summary?.top_calls || []
  const topPuts = summary?.top_puts || []

  // Capital calculation
  const allocatedRisk = summary?.allocated_risk_usd ?? 0
  const maxOpenRisk = summary?.max_open_risk_usd ?? 100
  const capPct = maxOpenRisk > 0 ? Math.min(100, Math.round((allocatedRisk / maxOpenRisk) * 100)) : 0

  const th: React.CSSProperties = { textAlign: 'left', color: '#666', fontSize: 10, textTransform: 'uppercase', padding: '10px 12px' }
  const td: React.CSSProperties = { color: '#AAA', fontSize: 12, padding: '10px 12px', borderTop: '1px solid rgba(255,255,255,0.04)' }
  const sel_: React.CSSProperties = { background: 'rgba(255,255,255,0.05)', color: '#DDD', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, padding: '7px 12px', fontSize: 12 }

  return (
    <OptionsShell title="Options Opportunities" active="/options/opportunities">
      {/* HEADER & TOP ACTIONS */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 16, marginBottom: 16 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <h1 style={{ fontSize: 24, fontWeight: 900, color: '#FFF', margin: 0, letterSpacing: '-0.5px' }}>
              🎯 Oportunidades de Opciones (CALL & PUT)
            </h1>
            <span style={{ fontSize: 10, padding: '3px 10px', borderRadius: 20, background: 'rgba(34,197,94,0.15)', color: '#22C55E', fontWeight: 800, border: '1px solid rgba(34,197,94,0.3)' }}>
              ARBITRAJE ADX & SIPV 1H
            </span>
          </div>
          <p style={{ color: '#777', fontSize: 12, margin: '4px 0 0 0' }}>
            Filtradas cada 5 min con los 4 catalizadores (Gap&Go, Basis 1H, ADX Wilder, Rebote) y validadas por ADUANA.
          </p>
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <button
            onClick={triggerCatalystScan}
            disabled={scanning}
            style={{
              background: scanning ? 'rgba(255,255,255,0.05)' : 'linear-gradient(135deg, #AB47BC 0%, #7B1FA2 100%)',
              color: scanning ? '#666' : '#FFF',
              border: 'none',
              borderRadius: 8,
              padding: '9px 16px',
              fontSize: 12,
              fontWeight: 800,
              cursor: scanning ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              boxShadow: scanning ? 'none' : '0 4px 14px rgba(171,71,188,0.3)',
            }}
          >
            {scanning ? '⏳ Escaneando 5m…' : '⚡ Escanear Catalizadores'}
          </button>

          <button
            onClick={triggerPortfolio}
            disabled={runningSelect}
            style={{
              background: runningSelect ? 'rgba(255,255,255,0.05)' : 'rgba(38, 166, 154, 0.2)',
              color: runningSelect ? '#666' : '#26A69A',
              border: '1px solid rgba(38, 166, 154, 0.4)',
              borderRadius: 8,
              padding: '9px 16px',
              fontSize: 12,
              fontWeight: 700,
              cursor: runningSelect ? 'not-allowed' : 'pointer',
            }}
          >
            {runningSelect ? 'Calculando…' : '↻ Re-evaluar Cartera'}
          </button>
        </div>
      </div>

      {msg && (
        <div style={{ background: 'rgba(34,197,94,0.15)', border: '1px solid rgba(34,197,94,0.3)', color: '#22C55E', borderRadius: 8, padding: '10px 14px', fontSize: 12, marginBottom: 14 }}>
          {msg}
        </div>
      )}
      {err && (
        <div style={{ background: 'rgba(239,83,80,0.15)', border: '1px solid rgba(239,83,80,0.3)', color: '#EF5350', borderRadius: 8, padding: '10px 14px', fontSize: 12, marginBottom: 14 }}>
          {err}
        </div>
      )}

      {/* CAPITAL ALLOCATION & RISK BAR (Stocks Style) */}
      {summary && (
        <div style={{
          background: 'linear-gradient(145deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%)',
          border: '1px solid rgba(255,255,255,0.08)',
          borderRadius: 14,
          padding: '16px 20px',
          marginBottom: 20,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10, flexWrap: 'wrap', gap: 10 }}>
            <div style={{ display: 'flex', gap: 20, fontSize: 12, fontWeight: 700 }}>
              <span>RIESGO ABIERTO ASIGNADO: <b style={{ color: '#22C55E' }}>${n(summary.allocated_risk_usd, 0)}</b></span>
              <span>RIESGO MÁXIMO TEÓRICO: <b style={{ color: '#FFF' }}>${n(summary.max_open_risk_usd, 0)}</b></span>
              <span>PRESUPUESTO DISPONIBLE: <b style={{ color: summary.remaining_budget_usd > 0 ? '#38BDF8' : '#EF5350' }}>${n(summary.remaining_budget_usd, 0)}</b></span>
            </div>
            <div style={{ display: 'flex', gap: 12, fontSize: 11, fontWeight: 800 }}>
              <span style={{ color: '#22C55E', background: 'rgba(34,197,94,0.1)', padding: '3px 8px', borderRadius: 4 }}>
                🟢 CALLs: {summary.total_calls ?? 0} / {summary.max_candidates_per_direction ?? 25} máx
              </span>
              <span style={{ color: '#AB47BC', background: 'rgba(171,71,188,0.1)', padding: '3px 8px', borderRadius: 4 }}>
                🟣 PUTs: {summary.total_puts ?? 0} / {summary.max_candidates_per_direction ?? 25} máx
              </span>
              <span style={{ color: '#FFD700', background: 'rgba(255,215,0,0.1)', padding: '3px 8px', borderRadius: 4 }}>
                ★ Seleccionadas: {summary.selected_count} / 3 día
              </span>
            </div>
          </div>
          <div style={{ height: 7, background: 'rgba(255,255,255,0.06)', borderRadius: 4, overflow: 'hidden' }}>
            <div style={{
              width: `${capPct}%`,
              height: '100%',
              background: 'linear-gradient(90deg, #22C55E 0%, #38BDF8 50%, #AB47BC 100%)',
              transition: 'width 0.8s ease',
              boxShadow: '0 0 10px rgba(34,197,94,0.3)',
            }} />
          </div>
        </div>
      )}

      {/* TOP 3 CALLS & TOP 3 PUTS PANELS (Stocks Priority Queue) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(480px, 1fr))', gap: 16, marginBottom: 20 }}>
        {/* TOP CALLS */}
        <div style={{
          background: 'linear-gradient(145deg, rgba(34,197,94,0.05) 0%, rgba(0,0,0,0.2) 100%)',
          border: '1px solid rgba(34,197,94,0.2)',
          borderRadius: 14,
          padding: 18,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>🟢</span>
              <h3 style={{ fontSize: 14, fontWeight: 900, color: '#FFF', margin: 0 }}>
                TOP 3 CALL (Foco Alcista / Rebote)
              </h3>
            </div>
            <span style={{ fontSize: 10, color: '#22C55E', fontWeight: 800, background: 'rgba(34,197,94,0.15)', padding: '3px 8px', borderRadius: 4 }}>
              LÍDERES ALCISTAS
            </span>
          </div>

          {topCalls.length === 0 ? (
            <div style={{ color: '#666', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>
              Sin candidatos CALL activos en este ciclo.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {topCalls.map((c: any) => (
                <div
                  key={c.id}
                  style={{
                    background: 'rgba(0,0,0,0.35)',
                    border: '1px solid rgba(255,255,255,0.05)',
                    borderRadius: 10,
                    padding: '12px 14px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ color: '#FFF', fontWeight: 900, fontSize: 14 }}>
                        {c.opt_underlyings?.symbol}
                      </span>
                      <span style={{ fontSize: 11, color: '#22C55E', fontWeight: 700 }}>
                        {STRAT[c.strategy_type] || c.strategy_type}
                      </span>
                      <ScoreBadge score={c.score} />
                    </div>
                    <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>
                      Vence: {c.expiry} · Débito: ${n(c.entry_debit)} · Max Pérdida: ${n(c.max_loss_total)}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      <CatalystSemaphores meta={c.catalyst_state || c.opt_underlyings?.catalyst_meta} />
                    </div>
                  </div>

                  <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
                    <StatusBadge status={c.eligibility_status} />
                    <button
                      onClick={() => handleSimulateEntry(c.id)}
                      disabled={simulating || c.eligibility_status === 'rejected'}
                      style={{
                        background: c.eligibility_status === 'rejected' ? 'rgba(255,255,255,0.05)' : 'rgba(34,197,94,0.2)',
                        color: c.eligibility_status === 'rejected' ? '#666' : '#22C55E',
                        border: '1px solid rgba(34,197,94,0.4)',
                        borderRadius: 6,
                        padding: '5px 10px',
                        fontSize: 10,
                        fontWeight: 800,
                        cursor: c.eligibility_status === 'rejected' ? 'not-allowed' : 'pointer',
                      }}
                    >
                      ★ Entrada Paper
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* TOP PUTS */}
        <div style={{
          background: 'linear-gradient(145deg, rgba(171,71,188,0.05) 0%, rgba(0,0,0,0.2) 100%)',
          border: '1px solid rgba(171,71,188,0.2)',
          borderRadius: 14,
          padding: 18,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 16 }}>🟣</span>
              <h3 style={{ fontSize: 14, fontWeight: 900, color: '#FFF', margin: 0 }}>
                TOP 3 PUT (Foco Bajista / Cayendo)
              </h3>
            </div>
            <span style={{ fontSize: 10, color: '#AB47BC', fontWeight: 800, background: 'rgba(171,71,188,0.15)', padding: '3px 8px', borderRadius: 4 }}>
              LÍDERES BAJISTAS
            </span>
          </div>

          {topPuts.length === 0 ? (
            <div style={{ color: '#666', fontSize: 12, padding: '20px 0', textAlign: 'center' }}>
              Sin candidatos PUT activos en este ciclo.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {topPuts.map((c: any) => (
                <div
                  key={c.id}
                  style={{
                    background: 'rgba(0,0,0,0.35)',
                    border: '1px solid rgba(255,255,255,0.05)',
                    borderRadius: 10,
                    padding: '12px 14px',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 12,
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ color: '#FFF', fontWeight: 900, fontSize: 14 }}>
                        {c.opt_underlyings?.symbol}
                      </span>
                      <span style={{ fontSize: 11, color: '#AB47BC', fontWeight: 700 }}>
                        {STRAT[c.strategy_type] || c.strategy_type}
                      </span>
                      <ScoreBadge score={c.score} />
                    </div>
                    <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>
                      Vence: {c.expiry} · Débito: ${n(c.entry_debit)} · Max Pérdida: ${n(c.max_loss_total)}
                    </div>
                    <div style={{ marginTop: 6 }}>
                      <CatalystSemaphores meta={c.catalyst_state || c.opt_underlyings?.catalyst_meta} />
                    </div>
                  </div>

                  <div style={{ textAlign: 'right', display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
                    <StatusBadge status={c.eligibility_status} />
                    <button
                      onClick={() => handleSimulateEntry(c.id)}
                      disabled={simulating || c.eligibility_status === 'rejected'}
                      style={{
                        background: c.eligibility_status === 'rejected' ? 'rgba(255,255,255,0.05)' : 'rgba(171,71,188,0.2)',
                        color: c.eligibility_status === 'rejected' ? '#666' : '#AB47BC',
                        border: '1px solid rgba(171,71,188,0.4)',
                        borderRadius: 6,
                        padding: '5px 10px',
                        fontSize: 10,
                        fontWeight: 800,
                        cursor: c.eligibility_status === 'rejected' ? 'not-allowed' : 'pointer',
                      }}
                    >
                      ★ Entrada Paper
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* FILTER & SEARCH CONTROLS */}
      <div style={optCard}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            <div style={{ display: 'flex', background: 'rgba(0,0,0,0.3)', padding: 3, borderRadius: 8, border: '1px solid rgba(255,255,255,0.05)' }}>
              <button
                onClick={() => setDirection('all')}
                style={{
                  padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, border: 'none', cursor: 'pointer',
                  background: direction === 'all' ? 'rgba(255,255,255,0.1)' : 'transparent',
                  color: direction === 'all' ? '#FFF' : '#888',
                }}
              >
                Todas ({items.length})
              </button>
              <button
                onClick={() => setDirection('bullish')}
                style={{
                  padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, border: 'none', cursor: 'pointer',
                  background: direction === 'bullish' ? 'rgba(34,197,94,0.2)' : 'transparent',
                  color: direction === 'bullish' ? '#22C55E' : '#888',
                }}
              >
                🟢 Solo CALLs
              </button>
              <button
                onClick={() => setDirection('bearish')}
                style={{
                  padding: '6px 12px', borderRadius: 6, fontSize: 11, fontWeight: 700, border: 'none', cursor: 'pointer',
                  background: direction === 'bearish' ? 'rgba(171,71,188,0.2)' : 'transparent',
                  color: direction === 'bearish' ? '#AB47BC' : '#888',
                }}
              >
                🟣 Solo PUTs
              </button>
            </div>

            <select style={sel_} value={status} onChange={e => setStatus(e.target.value)}>
              <option value="all">Todos los estados</option>
              <option value="selected">★ Seleccionadas (cartera)</option>
              <option value="eligible">Elegibles (ADUANA ok)</option>
              <option value="rejected">Descartadas</option>
            </select>

            <select style={sel_} value={strategy} onChange={e => setStrategy(e.target.value)}>
              <option value="">Todas las estrategias</option>
              <option value="long_call">Long Call</option>
              <option value="long_put">Long Put</option>
              <option value="bull_call_spread">Bull Call Spread</option>
              <option value="bear_put_spread">Bear Put Spread</option>
            </select>
          </div>

          <div style={{ display: 'flex', gap: 10 }}>
            <input
              type="text"
              placeholder="Filtrar por símbolo…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 6,
                padding: '6px 12px',
                color: '#FFF',
                fontSize: 12,
                outline: 'none',
                width: 180,
              }}
            />
            <button
              onClick={loadData}
              disabled={loading}
              style={{
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                color: '#AAA',
                borderRadius: 6,
                padding: '6px 12px',
                fontSize: 12,
                cursor: 'pointer',
              }}
            >
              ↻ Refrescar
            </button>
          </div>
        </div>

        {/* CANDIDATES TABLE */}
        {loading ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>Cargando oportunidades…</div>
        ) : items.length === 0 ? (
          <div style={{ padding: '40px', textAlign: 'center', color: '#666' }}>
            No hay candidatas con los filtros actuales.
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: 'rgba(0,0,0,0.2)' }}>
                  <th style={th}>Rank</th>
                  <th style={th}>Símbolo</th>
                  <th style={th}>Estrategia</th>
                  <th style={th}>Dirección</th>
                  <th style={th}>Vence</th>
                  <th style={th}>Piernas</th>
                  <th style={th}>Débito</th>
                  <th style={th}>Qty</th>
                  <th style={th}>Max Loss</th>
                  <th style={th}>EV Neto</th>
                  <th style={th}>Catalizadores</th>
                  <th style={th}>Score</th>
                  <th style={th}>Estado</th>
                </tr>
              </thead>
              <tbody>
                {items.map(c => {
                  const isCall = (c.direction || '').toLowerCase() === 'bullish'
                  return (
                    <Fragment key={c.id}>
                      <tr
                        onClick={() => openDetail(c.id)}
                        style={{
                          cursor: 'pointer',
                          background: sel === c.id ? 'rgba(255,255,255,0.04)' : 'transparent',
                          transition: 'background 0.2s',
                        }}
                      >
                        <td style={{ ...td, color: '#777' }}>
                          {c.rank_global ? `#${c.rank_global}` : '—'}
                        </td>
                        <td style={{ ...td, color: '#FFF', fontWeight: 800 }}>
                          {c.opt_underlyings?.symbol}
                        </td>
                        <td style={td}>{STRAT[c.strategy_type] || c.strategy_type}</td>
                        <td style={td}>
                          <span style={{
                            padding: '2px 6px',
                            borderRadius: 4,
                            background: isCall ? 'rgba(34,197,94,0.15)' : 'rgba(171,71,188,0.15)',
                            color: isCall ? '#22C55E' : '#AB47BC',
                            fontWeight: 800,
                            fontSize: 10,
                          }}>
                            {isCall ? '▲ CALL' : '▼ PUT'}
                          </span>
                        </td>
                        <td style={td}>{c.expiry}</td>
                        <td style={td}>
                          {(c.legs || []).map((l: any) => l.desc ?? `${l.side === 'buy' ? '+' : '−'}${l.right}${l.strike}`).join(' / ')}
                        </td>
                        <td style={td}>{c.eligibility_status === 'rejected' ? '—' : `$${n(c.entry_debit)}`}</td>
                        <td style={td}>{c.qty ?? '—'}</td>
                        <td style={td}>{c.max_loss_total != null ? `$${n(c.max_loss_total)}` : '—'}</td>
                        <td style={{ ...td, color: (c.ev_view_net || 0) > 0 ? '#22C55E' : '#AAA' }}>
                          {c.ev_view_net != null ? `$${n(c.ev_view_net)}` : '—'}
                        </td>
                        <td style={td}>
                          <CatalystSemaphores meta={c.catalyst_state || c.opt_underlyings?.catalyst_meta} />
                        </td>
                        <td style={td}>
                          <ScoreBadge score={c.score} />
                        </td>
                        <td style={td}>
                          <StatusBadge status={c.eligibility_status} />
                        </td>
                      </tr>

                      {/* EXPANDED ROW DETAIL */}
                      {sel === c.id && (
                        <tr>
                          <td colSpan={13} style={{ ...td, background: 'rgba(255,255,255,0.02)', padding: 18 }}>
                            {!detail ? (
                              <div style={{ color: '#888' }}>Cargando detalle de la candidata…</div>
                            ) : (
                              <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                                <div style={{ minWidth: 360, flex: 1 }}>
                                  {c.eligibility_status === 'rejected' ? (
                                    <>
                                      <b style={{ color: '#EF5350', fontSize: 13 }}>Motivos de Descarte (ADUANA / EV)</b>
                                      <ul style={{ margin: '8px 0 0', paddingLeft: 18, color: '#CCC', fontSize: 12, lineHeight: 1.6 }}>
                                        {(detail.rejection_reasons || []).map((r: string, idx: number) => <li key={idx}>{r}</li>)}
                                      </ul>
                                    </>
                                  ) : (
                                    <>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <b style={{ color: '#FFF', fontSize: 13 }}>Estructura & Griegas</b>
                                        {detail.budget_adapted && (
                                          <span style={{ fontSize: 11, color: '#FFA726', background: 'rgba(255, 167, 38, 0.15)', padding: '2px 8px', borderRadius: 4 }}>
                                            {detail.adaptation_note || 'Tamaño adaptado para entrar en presupuesto'}
                                          </span>
                                        )}
                                      </div>

                                      {detail.score_breakdown && (
                                        <div style={{ marginTop: 10, background: 'rgba(255,255,255,0.03)', padding: 10, borderRadius: 6, border: '1px solid rgba(255,255,255,0.05)' }}>
                                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                                            <b style={{ color: '#38BDF8', fontSize: 12 }}>Options Score: {detail.score?.toFixed(1)} / 100</b>
                                            <span style={{ fontSize: 11, color: '#888' }}>Mínimo req: {detail.score_breakdown.min_score_required}</span>
                                          </div>
                                          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, fontSize: 11 }}>
                                            <div>Expectativa (30%): <b style={{ color: '#FFF' }}>{detail.score_breakdown.components?.expectancy?.score?.toFixed(0)}</b></div>
                                            <div>Señal/Catalizador (20%): <b style={{ color: '#FFF' }}>{detail.score_breakdown.components?.apex_signal?.score?.toFixed(0)}</b></div>
                                            <div>Liquidez (20%): <b style={{ color: '#FFF' }}>{detail.score_breakdown.components?.liquidity?.score?.toFixed(0)}</b></div>
                                            <div>Riesgo (15%): <b style={{ color: '#FFF' }}>{detail.score_breakdown.components?.risk?.score?.toFixed(0)}</b></div>
                                            <div>IV/Griegas (10%): <b style={{ color: '#FFF' }}>{detail.score_breakdown.components?.iv_greeks?.score?.toFixed(0)}</b></div>
                                            <div>Contexto (5%): <b style={{ color: '#FFF' }}>{detail.score_breakdown.components?.context?.score?.toFixed(0)}</b></div>
                                          </div>
                                        </div>
                                      )}

                                      <table style={{ marginTop: 10, width: '100%' }}>
                                        <tbody>
                                          {(detail.legs || []).map((l: any, idx: number) => (
                                            <tr key={idx}>
                                              <td style={{ ...td, color: l.side === 'buy' ? '#22C55E' : '#EF5350' }}>{l.side === 'buy' ? 'COMPRA' : 'VENTA'}</td>
                                              <td style={td}>{l.right} {l.strike}</td>
                                              <td style={td}>bid {n(l.bid)} / ask {n(l.ask)}</td>
                                              <td style={td}>IV {n(l.iv, 3)}</td>
                                              <td style={td}>Δ {n(l.delta, 3)}</td>
                                              <td style={td}>{l.market_data_type}</td>
                                            </tr>
                                          ))}
                                        </tbody>
                                      </table>

                                      <div style={{ marginTop: 8, lineHeight: 1.7, fontSize: 11 }}>
                                        Costes/contrato: ${n(detail.costs_contract)} · Sobrecoste de ejecución: {detail.exec_overcost_pct != null ? `${n(detail.exec_overcost_pct, 1)}%` : '—'}<br />
                                        Plan de salida: {Object.entries(detail.exit_plan || {}).map(([k, v]) => `${k}=${v}`).join(' · ')}
                                      </div>

                                      {detail.aduana && (
                                        <div style={{ marginTop: 8, color: '#888', fontSize: 11 }}>
                                          ADUANA ({detail.aduana.approved ? 'aprobada' : 'rechazada'}): {detail.aduana.rules.map((r: any) => `${r.rule} ${r.ok ? '✓' : '✗'}`).join(' · ')}
                                        </div>
                                      )}

                                      <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
                                        <button
                                          onClick={() => handleSimulateEntry(c.id)}
                                          disabled={simulating}
                                          style={{
                                            background: simulating ? 'rgba(255,255,255,0.05)' : 'rgba(255, 215, 0, 0.2)',
                                            color: simulating ? '#888' : '#FFD700',
                                            border: '1px solid rgba(255, 215, 0, 0.4)',
                                            borderRadius: 6,
                                            padding: '8px 16px',
                                            fontSize: 11,
                                            fontWeight: 800,
                                            cursor: simulating ? 'not-allowed' : 'pointer',
                                          }}
                                        >
                                          {simulating ? 'Simulando…' : '★ Abrir Posición Paper'}
                                        </button>
                                        <span style={{ color: '#888', fontSize: 11 }}>
                                          Abre posición simulada en "Positions" con fills conservadores y salida monitoreada.
                                        </span>
                                      </div>
                                    </>
                                  )}
                                </div>

                                {c.eligibility_status !== 'rejected' && (
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    <Payoff data={detail.payoff} be={detail.breakeven != null ? Number(detail.breakeven) : null} />
                                  </div>
                                )}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </OptionsShell>
  )
}
