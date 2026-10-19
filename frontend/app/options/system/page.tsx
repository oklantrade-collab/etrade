'use client'
import { useEffect, useState } from 'react'
import { OptionsShell, optCard } from '@/components/options/OptionsShell'

export default function OptionsSystemPage() {
  const [health, setHealth] = useState<any>(null)
  const [auditEvents, setAuditEvents] = useState<any[]>([])
  const [calendarEvents, setCalendarEvents] = useState<Record<string, any>>({})
  const [calendarSymbols, setCalendarSymbols] = useState('SPY,QQQ,AAPL,NVDA,MSFT,AMZN,TSLA')
  const [loading, setLoading] = useState(true)
  const [actionMsg, setActionMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [killReason, setKillReason] = useState('')

  const loadData = async () => {
    setLoading(true)
    try {
      const [hRes, aRes, cRes] = await Promise.all([
        fetch('/api/v1/options/health').then(r => r.json()),
        fetch('/api/v1/options/control/audit?limit=20').then(r => r.json()),
        fetch(`/api/v1/options/events/calendar?symbols=${encodeURIComponent(calendarSymbols)}`).then(r => r.json()),
      ])
      setHealth(hRes)
      setAuditEvents(aRes.events || [])
      setCalendarEvents(cRes.events || {})
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    const t = setInterval(loadData, 15000)
    return () => clearInterval(t)
  }, [calendarSymbols])

  const toggleKillSwitch = async (active: boolean) => {
    const reason = killReason.trim() || (active ? 'Activación manual desde UI' : 'Desactivación manual desde UI')
    if (active && !confirm('¿Está seguro de activar el Kill Switch de emergencia? Se cancelarán y bloquearán todas las nuevas aperturas simuladas.')) {
      return
    }
    try {
      const res = await fetch('/api/v1/options/control/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active, reason }),
      })
      const d = await res.json()
      if (res.ok) {
        setActionMsg({ ok: true, text: `Kill Switch ${active ? 'ACTIVADO' : 'DESACTIVADO'} con éxito.` })
        setKillReason('')
        loadData()
      } else {
        setActionMsg({ ok: false, text: d.detail || 'Error al actualizar Kill Switch' })
      }
    } catch (e: any) {
      setActionMsg({ ok: false, text: e.message })
    }
  }

  const statusColor = health?.status === 'NORMAL' ? '#26A69A' : health?.status === 'DEGRADED' ? '#FFA726' : '#EF5350'
  const canOpenColor = health?.can_open_new_position ? '#26A69A' : '#EF5350'

  return (
    <OptionsShell title="Salud y Control del Sistema" active="/options/system">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
        {actionMsg && (
          <div style={{
            padding: '12px 16px', borderRadius: 10,
            background: actionMsg.ok ? 'rgba(38,166,154,0.1)' : 'rgba(239,83,80,0.1)',
            border: `1px solid ${actionMsg.ok ? '#26A69A' : '#EF5350'}`,
            color: actionMsg.ok ? '#26A69A' : '#EF5350', fontSize: 13, fontWeight: 600,
          }}>
            {actionMsg.text}
          </div>
        )}

        {/* Top Cards: Health & Kill Switch */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
          {/* Card 1: Estado Integral */}
          <div style={optCard}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: '#888', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                Máquina de Estado de Salud (Doc §4)
              </span>
              <span style={{
                padding: '4px 12px', borderRadius: 12, fontWeight: 900, fontSize: 12,
                background: `${statusColor}22`, border: `1px solid ${statusColor}`, color: statusColor,
              }}>
                {health?.status || 'CARGANDO...'}
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, fontSize: 13 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 6 }}>
                <span style={{ color: '#aaa' }}>Gate Fail-Closed (Nuevas Entradas):</span>
                <span style={{ color: canOpenColor, fontWeight: 800 }}>
                  {health?.can_open_new_position ? 'AUTORIZADAS' : 'BLOQUEADAS'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 6 }}>
                <span style={{ color: '#aaa' }}>Estado de Datos:</span>
                <span style={{ color: '#FFF', fontWeight: 700 }}>{health?.data_state || 'UNKNOWN'}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: 6 }}>
                <span style={{ color: '#aaa' }}>Divergencias Consecutivas:</span>
                <span style={{ color: '#FFF' }}>{health?.consecutive_divergences ?? 0}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#aaa' }}>Ratio de Cotizaciones Diferidas:</span>
                <span style={{ color: '#FFF' }}>{((health?.delayed_quotes_ratio || 0) * 100).toFixed(1)}%</span>
              </div>
            </div>

            {health?.reasons?.length > 0 && (
              <div style={{ marginTop: 14, padding: '10px 12px', borderRadius: 8, background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#FFA726', marginBottom: 4 }}>Motivos de estado:</div>
                <ul style={{ margin: 0, paddingLeft: 16, fontSize: 12, color: '#ddd' }}>
                  {health.reasons.map((r: string, idx: number) => <li key={idx}>{r}</li>)}
                </ul>
              </div>
            )}
          </div>

          {/* Card 2: Kill Switch de Emergencia */}
          <div style={{ ...optCard, border: health?.kill_switch_active ? '1px solid rgba(239,83,80,0.4)' : optCard.border }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: '#888', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
                Kill Switch de Emergencia (§4.2)
              </span>
              <span style={{
                padding: '4px 12px', borderRadius: 12, fontWeight: 900, fontSize: 11,
                background: health?.kill_switch_active ? 'rgba(239,83,80,0.2)' : 'rgba(38,166,154,0.1)',
                border: `1px solid ${health?.kill_switch_active ? '#EF5350' : '#26A69A'}`,
                color: health?.kill_switch_active ? '#EF5350' : '#26A69A',
              }}>
                {health?.kill_switch_active ? 'ACTIVADO' : 'INACTIVO'}
              </span>
            </div>

            <p style={{ color: '#aaa', fontSize: 12, lineHeight: 1.5, margin: '0 0 14px 0' }}>
              Al activar el Kill Switch, el sistema pasa a estado <strong>HALTED</strong> inmediatamente: se bloquea toda nueva apertura en paper trading y se audita el motivo.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <input
                type="text"
                placeholder="Motivo del cambio de estado..."
                value={killReason}
                onChange={e => setKillReason(e.target.value)}
                style={{
                  padding: '8px 12px', borderRadius: 8, background: 'rgba(0,0,0,0.3)',
                  border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 12,
                }}
              />
              <div style={{ display: 'flex', gap: 10 }}>
                {health?.kill_switch_active ? (
                  <button
                    onClick={() => toggleKillSwitch(false)}
                    style={{
                      flex: 1, padding: '10px 16px', borderRadius: 8, border: 'none',
                      background: '#26A69A', color: '#FFF', fontWeight: 800, fontSize: 12, cursor: 'pointer',
                    }}
                  >
                    Reanudar Operación Normal (Desactivar)
                  </button>
                ) : (
                  <button
                    onClick={() => toggleKillSwitch(true)}
                    style={{
                      flex: 1, padding: '10px 16px', borderRadius: 8, border: 'none',
                      background: '#EF5350', color: '#FFF', fontWeight: 800, fontSize: 12, cursor: 'pointer',
                    }}
                  >
                    ACTIVAR KILL SWITCH DE EMERGENCIA
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Section 2: Hybrid Event Calendar */}
        <div style={optCard}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14, flexWrap: 'wrap', gap: 10 }}>
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: '#FFF' }}>
                Calendario Híbrido de Eventos (Doc §7)
              </h3>
              <span style={{ fontSize: 11, color: '#777' }}>
                Fuente Primaria: Stocks Fundamentals/News | Fallback: IBKR Scanner | Estado canónico exigido: CLEAR_VERIFIED
              </span>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <input
                type="text"
                value={calendarSymbols}
                onChange={e => setCalendarSymbols(e.target.value)}
                style={{
                  padding: '6px 10px', borderRadius: 6, background: 'rgba(0,0,0,0.3)',
                  border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 12, width: 260,
                }}
              />
              <button
                onClick={loadData}
                style={{
                  padding: '6px 12px', borderRadius: 6, background: 'rgba(255,255,255,0.06)',
                  border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 12, cursor: 'pointer',
                }}
              >
                Actualizar
              </button>
            </div>
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ color: '#777', borderBottom: '1px solid rgba(255,255,255,0.08)', textAlign: 'left' }}>
                  <th style={{ padding: '8px 10px' }}>Símbolo</th>
                  <th style={{ padding: '8px 10px' }}>Estado Canónico</th>
                  <th style={{ padding: '8px 10px' }}>Tipo de Evento</th>
                  <th style={{ padding: '8px 10px' }}>Fecha Prevista</th>
                  <th style={{ padding: '8px 10px' }}>Filtro ADUANA (B-09)</th>
                  <th style={{ padding: '8px 10px' }}>Fuente</th>
                </tr>
              </thead>
              <tbody>
                {Object.keys(calendarEvents).length === 0 ? (
                  <tr>
                    <td colSpan={6} style={{ padding: 16, textAlign: 'center', color: '#666' }}>
                      Cargando o sin eventos para los símbolos seleccionados...
                    </td>
                  </tr>
                ) : (
                  Object.values(calendarEvents).map((ev: any) => {
                    const stColor = ev.state === 'CLEAR_VERIFIED' ? '#26A69A' : ev.state === 'EVENT_FOUND' ? '#EF5350' : '#FFA726'
                    return (
                      <tr key={ev.symbol} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                        <td style={{ padding: '10px', fontWeight: 800, color: '#FFF' }}>{ev.symbol}</td>
                        <td style={{ padding: '10px' }}>
                          <span style={{
                            padding: '3px 8px', borderRadius: 6, fontWeight: 800, fontSize: 11,
                            background: `${stColor}18`, border: `1px solid ${stColor}`, color: stColor,
                          }}>
                            {ev.state}
                          </span>
                        </td>
                        <td style={{ padding: '10px', color: '#ccc' }}>{ev.event_type || 'Ninguno detectado'}</td>
                        <td style={{ padding: '10px', color: '#aaa' }}>{ev.event_date ? ev.event_date.slice(0, 10) : 'Sin fecha'}</td>
                        <td style={{ padding: '10px' }}>
                          <span style={{ color: ev.is_blocking ? '#EF5350' : '#26A69A', fontWeight: 700 }}>
                            {ev.is_blocking ? 'BLOQUEADO' : 'APROBADO'}
                          </span>
                        </td>
                        <td style={{ padding: '10px', color: '#888' }}>{ev.source || 'hybrid'}</td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Section 3: Audit Trail Log */}
        <div style={optCard}>
          <h3 style={{ margin: '0 0 12px 0', fontSize: 16, fontWeight: 800, color: '#FFF' }}>
            Registro de Auditoría de Control y Seguridad (§17)
          </h3>
          <div style={{ overflowX: 'auto', maxHeight: 300 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr style={{ color: '#777', borderBottom: '1px solid rgba(255,255,255,0.08)', textAlign: 'left' }}>
                  <th style={{ padding: '8px 10px' }}>Fecha / Hora (UTC)</th>
                  <th style={{ padding: '8px 10px' }}>Evento</th>
                  <th style={{ padding: '8px 10px' }}>Operador</th>
                  <th style={{ padding: '8px 10px' }}>Motivo / Detalle</th>
                </tr>
              </thead>
              <tbody>
                {auditEvents.length === 0 ? (
                  <tr>
                    <td colSpan={4} style={{ padding: 16, textAlign: 'center', color: '#666' }}>
                      Sin eventos de control registrados recientemente.
                    </td>
                  </tr>
                ) : (
                  auditEvents.map((evt: any, i: number) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)' }}>
                      <td style={{ padding: '8px 10px', color: '#888' }}>{evt.created_at?.slice(0, 19).replace('T', ' ')}</td>
                      <td style={{ padding: '8px 10px', fontWeight: 700, color: '#FFF' }}>{evt.event_type}</td>
                      <td style={{ padding: '8px 10px', color: '#aaa' }}>{evt.triggered_by}</td>
                      <td style={{ padding: '8px 10px', color: '#ccc' }}>{evt.reason}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </OptionsShell>
  )
}
