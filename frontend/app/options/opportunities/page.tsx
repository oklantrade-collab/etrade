'use client'
import { Fragment, useEffect, useState } from 'react'
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
    bg = 'rgba(38, 166, 154, 0.2)'
    color = '#26A69A'
  } else if (sc >= 60) {
    bg = 'rgba(41, 182, 246, 0.2)'
    color = '#29B6F6'
  } else if (sc >= 45) {
    bg = 'rgba(255, 167, 38, 0.2)'
    color = '#FFA726'
  }
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: 4,
      background: bg,
      color,
      fontWeight: 700,
      fontSize: 11,
      minWidth: 32,
      textAlign: 'center',
    }}>
      {sc.toFixed(1)}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  if (status === 'selected') {
    return (
      <span style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        background: 'rgba(255, 215, 0, 0.2)',
        color: '#FFD700',
        fontWeight: 700,
        fontSize: 10,
        textTransform: 'uppercase',
      }}>
        ★ Seleccionada
      </span>
    )
  }
  if (status === 'eligible') {
    return (
      <span style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        background: 'rgba(38, 166, 154, 0.15)',
        color: '#26A69A',
        fontWeight: 600,
        fontSize: 10,
        textTransform: 'uppercase',
      }}>
        Elegible
      </span>
    )
  }
  if (status === 'rejected') {
    return (
      <span style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        background: 'rgba(239, 83, 80, 0.12)',
        color: '#EF5350',
        fontSize: 10,
        textTransform: 'uppercase',
      }}>
        Descartada
      </span>
    )
  }
  return <span style={{ color: '#888', fontSize: 10 }}>{status}</span>
}

function Payoff({ data, be }: { data: { price: number; pnl: number }[]; be: number | null }) {
  if (!data?.length) return <div style={{ color: '#666', fontSize: 12 }}>Sin curva (faltan datos).</div>
  const W = 420, H = 140, P = 24
  const xs = data.map(d => d.price), ys = data.map(d => d.pnl)
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys, 0), y1 = Math.max(...ys, 0)
  const sx = (x: number) => P + ((x - x0) / (x1 - x0 || 1)) * (W - 2 * P)
  const sy = (y: number) => H - P - ((y - y0) / (y1 - y0 || 1)) * (H - 2 * P)
  const path = data.map((d, i) => `${i ? 'L' : 'M'}${sx(d.price).toFixed(1)},${sy(d.pnl).toFixed(1)}`).join(' ')
  return (
    <svg width={W} height={H} style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8 }}>
      <line x1={P} x2={W - P} y1={sy(0)} y2={sy(0)} stroke="#444" strokeDasharray="3 3" />
      {be !== null && <line x1={sx(be)} x2={sx(be)} y1={P} y2={H - P} stroke="#AB47BC" strokeDasharray="3 3" />}
      <path d={path} fill="none" stroke="#26A69A" strokeWidth={2} />
      <text x={P} y={12} fill="#666" fontSize={10}>P&L al vencimiento (por contrato, neto de costes) · máx ${n(y1, 0)} / mín ${n(y0, 0)}</text>
      <text x={P} y={H - 6} fill="#666" fontSize={10}>${n(x0, 1)}</text>
      <text x={W - P - 30} y={H - 6} fill="#666" fontSize={10}>${n(x1, 1)}</text>
    </svg>
  )
}

export default function OptionsOpportunities() {
  const [items, setItems] = useState<any[]>([])
  const [summary, setSummary] = useState<any>(null)
  const [status, setStatus] = useState('all')
  const [strategy, setStrategy] = useState('')
  const [direction, setDirection] = useState('')
  const [sel, setSel] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)
  const [err, setErr] = useState<string | null>(null)
  const [runningSelect, setRunningSelect] = useState(false)

  const loadData = () => {
    const qs = new URLSearchParams({
      status,
      ...(strategy && { strategy }),
      ...(direction && { direction }),
    })
    fetch(`/api/v1/options/opportunities?${qs}`)
      .then(r => r.json())
      .then(d => {
        setItems(d.items || [])
        setSummary(d.summary || null)
        setErr(d.error || null)
      })
      .catch(() => setErr('API no disponible'))
  }

  useEffect(() => {
    loadData()
  }, [status, strategy, direction])

  const open = async (id: number) => {
    if (sel === id) { setSel(null); return }
    setSel(id); setDetail(null)
    setDetail(await fetch(`/api/v1/options/candidates/${id}`).then(r => r.json()).catch(() => null))
  }

  const triggerPortfolio = async () => {
    setRunningSelect(true)
    try {
      await fetch('/api/v1/options/portfolio/select', { method: 'POST' })
      loadData()
    } catch {
      setErr('Error al ejecutar el selector')
    } finally {
      setRunningSelect(false)
    }
  }

  const [msg, setMsg] = useState<string | null>(null)
  const [simulating, setSimulating] = useState(false)

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
        loadData()
      } else {
        setErr(res.detail || 'Error al simular entrada')
      }
    } catch {
      setErr('Error de red al conectar con la API')
    } finally {
      setSimulating(false)
    }
  }

  const th: React.CSSProperties = { textAlign: 'left', color: '#666', fontSize: 10, textTransform: 'uppercase', padding: '8px 10px' }
  const td: React.CSSProperties = { color: '#AAA', fontSize: 12, padding: '8px 10px', borderTop: '1px solid rgba(255,255,255,0.04)' }
  const sel_: React.CSSProperties = { background: 'rgba(255,255,255,0.05)', color: '#DDD', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 6, padding: '6px 10px', fontSize: 12 }
  const kpiCard: React.CSSProperties = { background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: 8, padding: '10px 14px', flex: 1, minWidth: 140 }

  return (
    <OptionsShell title="Options Opportunities" active="/options/opportunities">
      {/* KPIs Header (Sprint 5: Presupuesto y Selecciones de Cartera) */}
      {summary && (
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 14 }}>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Seleccionadas para Cartera</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#FFD700', marginTop: 4 }}>
              {summary.selected_count} <span style={{ fontSize: 12, color: '#888' }}>/ max 3 por día</span>
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Riesgo Abierto Asignado</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#26A69A', marginTop: 4 }}>
              ${n(summary.allocated_risk_usd, 0)} <span style={{ fontSize: 12, color: '#888' }}>/ ${n(summary.max_open_risk_usd, 0)} máx</span>
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Presupuesto Restante</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: summary.remaining_budget_usd > 0 ? '#29B6F6' : '#EF5350', marginTop: 4 }}>
              ${n(summary.remaining_budget_usd, 0)}
            </div>
          </div>
          <div style={kpiCard}>
            <div style={{ color: '#888', fontSize: 11, textTransform: 'uppercase' }}>Candidatas Elegibles</div>
            <div style={{ fontSize: 20, fontWeight: 700, color: '#DDD', marginTop: 4 }}>
              {summary.eligible_count} <span style={{ fontSize: 12, color: '#666' }}>({summary.total_candidates} total)</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <button
              onClick={triggerPortfolio}
              disabled={runningSelect}
              style={{
                background: runningSelect ? 'rgba(255,255,255,0.05)' : 'rgba(38, 166, 154, 0.2)',
                color: runningSelect ? '#666' : '#26A69A',
                border: '1px solid rgba(38, 166, 154, 0.4)',
                borderRadius: 6,
                padding: '8px 14px',
                fontSize: 12,
                cursor: runningSelect ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              {runningSelect ? 'Calculando…' : '↻ Re-evaluar Cartera'}
            </button>
          </div>
        </div>
      )}

      <div style={optCard}>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
          <select style={sel_} value={status} onChange={e => setStatus(e.target.value)}>
            <option value="all">Todas las candidatas</option>
            <option value="selected">★ Seleccionadas (cartera activa)</option>
            <option value="eligible">Elegibles (ADUANA y EV OK)</option>
            <option value="rejected">Descartadas (con motivo)</option>
            <option value="pending">Pendientes de valoración</option>
          </select>
          <select style={sel_} value={strategy} onChange={e => setStrategy(e.target.value)}>
            <option value="">Todas las estrategias</option>
            {Object.entries(STRAT).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
          <select style={sel_} value={direction} onChange={e => setDirection(e.target.value)}>
            <option value="">Ambas direcciones</option>
            <option value="bullish">Alcista (▲)</option>
            <option value="bearish">Bajista (▼)</option>
          </select>
        </div>

        <div style={{ color: '#777', fontSize: 11, marginBottom: 10 }}>
          Sprint 5: Ranking global y por estrategia mediante Options Score (0–100). Selector greedy de cartera con restricciones de presupuesto (§11 y §12).
        </div>

        {msg && <div style={{ background: 'rgba(38, 166, 154, 0.15)', border: '1px solid #26A69A', color: '#26A69A', padding: '8px 12px', borderRadius: 6, marginBottom: 10, fontSize: 12 }}>{msg}</div>}
        {err && <div style={{ color: '#EF5350', fontSize: 12, marginBottom: 8 }}>{err}</div>}
        {items.length === 0 && !err && (
          <div style={{ color: '#666', fontSize: 13, padding: '20px 0', textAlign: 'center' }}>
            Sin candidatas para los filtros seleccionados. Ejecute un scan o re-evalúe la cartera.
          </div>
        )}

        {items.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr>
                <th style={th}>Rank</th>
                <th style={th}>Ticker</th>
                <th style={th}>Estrategia</th>
                <th style={th}>Dir.</th>
                <th style={th}>Venc.</th>
                <th style={th}>Piernas</th>
                <th style={th}>Débito</th>
                <th style={th}>Qty</th>
                <th style={th}>Pérd. máx</th>
                <th style={th}>EV neto</th>
                <th style={th}>Score</th>
                <th style={th}>Estado</th>
              </tr>
            </thead>
            <tbody>
              {items.map(c => (
                <Fragment key={c.id}>
                  <tr onClick={() => open(c.id)} style={{ cursor: 'pointer', background: sel === c.id ? 'rgba(255,255,255,0.03)' : 'transparent' }}>
                    <td style={{ ...td, color: '#777' }}>
                      {c.rank_global ? `#${c.rank_global}` : '—'}
                    </td>
                    <td style={{ ...td, color: '#FFF', fontWeight: 700 }}>
                      {c.opt_underlyings?.symbol}
                    </td>
                    <td style={td}>{STRAT[c.strategy_type] || c.strategy_type}</td>
                    <td style={td}>
                      {c.direction === 'bullish' ? '▲' : '▼'}{c.direction_source === 'unverified' ? ' *' : ''}
                    </td>
                    <td style={td}>{c.expiry}</td>
                    <td style={td}>
                      {(c.legs || []).map((l: any) => l.desc ?? `${l.side === 'buy' ? '+' : '−'}${l.right}${l.strike}`).join(' / ')}
                    </td>
                    <td style={td}>{c.eligibility_status === 'rejected' ? '—' : n(c.entry_debit)}</td>
                    <td style={td}>{c.qty ?? '—'}</td>
                    <td style={td}>{c.max_loss_total != null ? `$${n(c.max_loss_total)}` : '—'}</td>
                    <td style={{ ...td, color: (c.ev_view_net || 0) > 0 ? '#26A69A' : '#AAA' }}>
                      {c.ev_view_net != null ? `$${n(c.ev_view_net)}` : '—'}
                    </td>
                    <td style={td}>
                      <ScoreBadge score={c.score} />
                    </td>
                    <td style={td}>
                      <StatusBadge status={c.eligibility_status} />
                    </td>
                  </tr>

                  {sel === c.id && (
                    <tr>
                      <td colSpan={12} style={{ ...td, background: 'rgba(255,255,255,0.02)', padding: '16px' }}>
                        {!detail ? 'Cargando detalle…' : (
                          <div style={{ display: 'flex', gap: 24, flexWrap: 'wrap' }}>
                            <div style={{ minWidth: 340, flex: 1 }}>
                              {c.eligibility_status === 'rejected' ? (
                                <>
                                  <b style={{ color: '#EF5350' }}>Motivos de descarte</b>
                                  <ul style={{ margin: '6px 0 0', paddingLeft: 18, color: '#CCC' }}>
                                    {(detail.rejection_reasons || []).map((r: string) => <li key={r}>{r}</li>)}
                                  </ul>
                                </>
                              ) : (
                                <>
                                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <b style={{ color: '#FFF', fontSize: 13 }}>Detalle de Estructura</b>
                                    {detail.budget_adapted && (
                                      <span style={{ fontSize: 11, color: '#FFA726', background: 'rgba(255, 167, 38, 0.15)', padding: '2px 8px', borderRadius: 4 }}>
                                        {detail.adaptation_note || 'Tamaño adaptado para entrar en presupuesto'}
                                      </span>
                                    )}
                                  </div>

                                  {/* Score Breakdown (Sprint 5) */}
                                  {detail.score_breakdown && (
                                    <div style={{ marginTop: 10, background: 'rgba(255,255,255,0.03)', padding: 10, borderRadius: 6 }}>
                                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                                        <b style={{ color: '#29B6F6', fontSize: 12 }}>Options Score: {detail.score?.toFixed(1)} / 100</b>
                                        <span style={{ fontSize: 11, color: '#888' }}>Mínimo req: {detail.score_breakdown.min_score_required}</span>
                                      </div>
                                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, fontSize: 11 }}>
                                        <div>Expectativa (30%): <b style={{ color: '#FFF' }}>{detail.score_breakdown.components?.expectancy?.score?.toFixed(0)}</b></div>
                                        <div>Señal APEX (20%): <b style={{ color: '#FFF' }}>{detail.score_breakdown.components?.apex_signal?.score?.toFixed(0)}</b></div>
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
                                          <td style={{ ...td, color: l.side === 'buy' ? '#26A69A' : '#EF5350' }}>{l.side === 'buy' ? 'COMPRA' : 'VENTA'}</td>
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

                                  {detail.simulation && (
                                    <div style={{ marginTop: 10, lineHeight: 1.7, fontSize: 11 }}>
                                      <b style={{ color: '#CCC' }}>Valoración teórica</b> (horizonte {detail.simulation.scenario_config.horizon_hours} h · σ_h {n(detail.simulation.scenario_config.sigma_h * 100, 2)}% · mov. esperado ±${n(detail.expected_move)} · α {detail.alpha_used}):<br />
                                      EV neutral ${n(detail.ev_neutral_net)} · EV con sesgo ${n(detail.ev_view_net)} · EV adverso ${n(detail.ev_view_adverse)} · peor escenario adverso ${n(detail.simulation.scenario_results.worst_adverse_pnl)}
                                    </div>
                                  )}

                                  {detail.aduana && (
                                    <div style={{ marginTop: 8, color: '#777', fontSize: 11 }}>
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
                                        padding: '7px 14px',
                                        fontSize: 11,
                                        fontWeight: 700,
                                        cursor: simulating ? 'not-allowed' : 'pointer',
                                      }}
                                    >
                                      {simulating ? 'Simulando…' : '★ Simular Entrada (Paper)'}
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
              ))}
            </tbody>
          </table>
        )}

        <div style={{ color: '#555', fontSize: 11, marginTop: 14 }}>
          * dirección no verificada por APEX: se generan ambos sentidos bajo modo de prueba.
        </div>
      </div>
    </OptionsShell>
  )
}
