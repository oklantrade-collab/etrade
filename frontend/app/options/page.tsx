'use client'
import { useEffect, useState } from 'react'
import Link from 'next/link'
import { OptionsShell, optCard, useOptionsStatus } from '@/components/options/OptionsShell'

function Kpi({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <div style={{ ...optCard, padding: 18 }}>
      <div style={{ fontSize: 10, fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.15em' }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 900, color: color || '#FFF', marginTop: 6 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function OptionsDashboard() {
  const { status, health, error } = useOptionsStatus()
  const [greeks, setGreeks] = useState<any>(null)
  const [calendar, setCalendar] = useState<any>(null)

  useEffect(() => {
    fetch('/api/v1/options/analytics/portfolio-greeks')
      .then(r => r.ok ? r.json() : null)
      .then(setGreeks)
      .catch(() => {})

    fetch('/api/v1/options/events/calendar?symbols=SPY,QQQ,AAPL,NVDA,MSFT')
      .then(r => r.ok ? r.json() : null)
      .then(setCalendar)
      .catch(() => {})
  }, [])

  const caps = status?.hard_caps
  const hStatus = health?.status ?? 'NORMAL'
  const hColor = hStatus === 'NORMAL' ? '#26A69A' : hStatus === 'DEGRADED' ? '#FFA726' : '#EF5350'
  const isKillActive = Boolean(health?.kill_switch_active)
  const totals = greeks?.portfolio_totals || {}
  const eventsCount = calendar?.events ? Object.keys(calendar.events).length : 0
  const verifiedCount = calendar?.events ? Object.values(calendar.events).filter((e: any) => e.state === 'CLEAR_VERIFIED').length : 0

  return (
    <OptionsShell title="Options Dashboard" active="/options">
      {error && <div style={{ ...optCard, color: '#EF5350', fontSize: 13 }}>No se pudo leer el estado del módulo (API {error}).</div>}

      {/* Top KPIs Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
        <Kpi
          label="Módulo & Modo"
          value={status?.module_enabled ? 'PAPER' : 'OFF'}
          sub="Sin órdenes reales por diseño"
          color="#26A69A"
        />
        <Kpi
          label="Salud del Sistema"
          value={hStatus}
          sub={health?.can_open_new_position ? 'Entradas autorizadas' : 'Nuevas entradas en pausa'}
          color={hColor}
        />
        <Kpi
          label="Kill Switch"
          value={isKillActive ? 'ACTIVADO' : 'INACTIVO'}
          sub={isKillActive ? 'Bloqueo total de emergencia' : 'Operación normal'}
          color={isKillActive ? '#EF5350' : '#26A69A'}
        />
        <Kpi
          label="Delta Cartera (USD)"
          value={totals.delta_usd != null ? `$${totals.delta_usd > 0 ? '+' : ''}${totals.delta_usd}` : '$0.00'}
          sub={`Theta: $${totals.theta_day ?? '0.00'}/día`}
          color={(totals.delta_usd || 0) >= 0 ? '#26A69A' : '#EF5350'}
        />
        <Kpi
          label="Techo Riesgo / Trade"
          value={caps ? `$${caps.max_risk_per_trade_usd}` : '$50'}
          sub={`Abierto: $${caps?.max_open_risk_usd ?? '100'}`}
        />
      </div>

      {/* Featured Architecture Modules Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 16 }}>
        {/* Module 1: Salud & Kill Switch */}
        <div style={{ ...optCard, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontSize: 18 }}>🛡️</span>
              <span style={{
                padding: '3px 8px', borderRadius: 6, fontSize: 10, fontWeight: 900,
                background: `${hColor}22`, border: `1px solid ${hColor}`, color: hColor, textTransform: 'uppercase',
              }}>
                {hStatus}
              </span>
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 900, color: '#FFF', margin: '0 0 6px 0' }}>
              Salud del Sistema & Kill Switch (Doc §4)
            </h3>
            <p style={{ fontSize: 12, color: '#888', lineHeight: 1.6, margin: '0 0 14px 0' }}>
              Máquina de estados Fail-Closed. Ante pérdida de datos LIVE o latencia anormal, el sistema pasa a <strong>DEGRADED</strong> o <strong>HALTED</strong> y pausa aperturas.
            </p>
            <div style={{ fontSize: 11, color: '#aaa', display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div>• Gate Fail-Closed: <b style={{ color: health?.can_open_new_position ? '#26A69A' : '#EF5350' }}>{health?.can_open_new_position ? 'AUTORIZADO' : 'EN PAUSA'}</b></div>
              <div>• Datos cotización: <b style={{ color: '#FFF' }}>{status?.worker?.data_state ?? 'UNKNOWN'}</b></div>
              <div>• Kill switch: <b style={{ color: isKillActive ? '#EF5350' : '#26A69A' }}>{isKillActive ? 'ACTIVO' : 'INACTIVO'}</b></div>
            </div>
          </div>
          <Link href="/options/system" style={{
            marginTop: 16, padding: '8px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 12, fontWeight: 700,
            textDecoration: 'none', textAlign: 'center', display: 'block',
          }}>
            Abrir Panel de Salud & Control →
          </Link>
        </div>

        {/* Module 2: Griegas Netas & Analítica */}
        <div style={{ ...optCard, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontSize: 18 }}>📐</span>
              <span style={{
                padding: '3px 8px', borderRadius: 6, fontSize: 10, fontWeight: 900,
                background: 'rgba(56, 189, 248, 0.15)', border: '1px solid #38BDF8', color: '#38BDF8',
              }}>
                MODEL ANALYTICS
              </span>
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 900, color: '#FFF', margin: '0 0 6px 0' }}>
              Griegas Netas & Strategy Lab (Doc §8)
            </h3>
            <p style={{ fontSize: 12, color: '#888', lineHeight: 1.6, margin: '0 0 14px 0' }}>
              Cálculo analítico Black-Scholes para cada pata y cartera agregada. Exposición Delta USD, curvatura Gamma, Vega y decaimiento Theta diario.
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, fontSize: 11, background: 'rgba(0,0,0,0.2)', padding: 10, borderRadius: 8 }}>
              <div>Δ Delta: <b style={{ color: '#FFF' }}>${totals.delta_usd ?? '0.00'}</b></div>
              <div>Γ Gamma: <b style={{ color: '#42A5F5' }}>{totals.gamma ?? '0.00'}</b></div>
              <div>V Vega: <b style={{ color: '#AB47BC' }}>${totals.vega_point ?? '0.00'}/pt</b></div>
              <div>Θ Theta: <b style={{ color: '#26A69A' }}>${totals.theta_day ?? '0.00'}/día</b></div>
            </div>
          </div>
          <Link href="/options/analytics" style={{
            marginTop: 16, padding: '8px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 12, fontWeight: 700,
            textDecoration: 'none', textAlign: 'center', display: 'block',
          }}>
            Ver Analítica & Griegas →
          </Link>
        </div>

        {/* Module 3: Calendario Híbrido de Eventos */}
        <div style={{ ...optCard, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontSize: 18 }}>📅</span>
              <span style={{
                padding: '3px 8px', borderRadius: 6, fontSize: 10, fontWeight: 900,
                background: 'rgba(38,166,154,0.15)', border: '1px solid #26A69A', color: '#26A69A',
              }}>
                HÍBRIDO
              </span>
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 900, color: '#FFF', margin: '0 0 6px 0' }}>
              Calendario Híbrido de Eventos (Doc §7)
            </h3>
            <p style={{ fontSize: 12, color: '#888', lineHeight: 1.6, margin: '0 0 14px 0' }}>
              Doble fuente para blindar contra sorpresas binarias: Fundamentals/Noticias de Stocks + escáner IBKR. Exige estado canónico <code>CLEAR_VERIFIED</code>.
            </p>
            <div style={{ fontSize: 11, color: '#aaa', display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div>• Símbolos monitorizados: <b style={{ color: '#FFF' }}>{eventsCount} tickers clave</b></div>
              <div>• Verificados sin eventos: <b style={{ color: '#26A69A' }}>{verifiedCount} / {eventsCount}</b></div>
              <div>• Política: <b style={{ color: '#FFA726' }}>UNKNOWN/STALE bloquea en Paper</b></div>
            </div>
          </div>
          <Link href="/options/system" style={{
            marginTop: 16, padding: '8px 14px', borderRadius: 8, background: 'rgba(255,255,255,0.05)',
            border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', fontSize: 12, fontWeight: 700,
            textDecoration: 'none', textAlign: 'center', display: 'block',
          }}>
            Consultar Calendario de Eventos →
          </Link>
        </div>

        {/* Module 4: Oportunidades & Score Explicable */}
        <div style={{ ...optCard, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
              <span style={{ fontSize: 18 }}>💡</span>
              <span style={{
                padding: '3px 8px', borderRadius: 6, fontSize: 10, fontWeight: 900,
                background: 'rgba(255, 215, 0, 0.15)', border: '1px solid rgba(255, 215, 0, 0.4)', color: '#FFD700',
              }}>
                OPPORTUNITIES
              </span>
            </div>
            <h3 style={{ fontSize: 16, fontWeight: 900, color: '#FFF', margin: '0 0 6px 0' }}>
              Oportunidades & Robustez EV (Doc §8.2, §9)
            </h3>
            <p style={{ fontSize: 12, color: '#888', lineHeight: 1.6, margin: '0 0 14px 0' }}>
              Ranking por Options Score explicable, semáforos de catalizadores, cálculo de <code>ev_robust</code> ante shocks de volatilidad y replay determinista.
            </p>
            <div style={{ fontSize: 11, color: '#aaa', display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div>• Filtro ADUANA ampliado: <b style={{ color: '#26A69A' }}>Reglas O-1 a O-16</b></div>
              <div>• Validación: <b style={{ color: '#FFF' }}>Cobertura mínima $\ge 80\%$</b></div>
              <div>• Top Priority Queues: <b style={{ color: '#FFF' }}>TOP 3 CALLs & TOP 3 PUTs</b></div>
            </div>
          </div>
          <Link href="/options/opportunities" style={{
            marginTop: 16, padding: '8px 14px', borderRadius: 8, background: 'rgba(255, 215, 0, 0.1)',
            border: '1px solid rgba(255, 215, 0, 0.3)', color: '#FFD700', fontSize: 12, fontWeight: 700,
            textDecoration: 'none', textAlign: 'center', display: 'block',
          }}>
            Explorar Oportunidades & EV →
          </Link>
        </div>
      </div>

      {/* Architecture Version and Compliance Banner */}
      <div style={optCard}>
        <div style={{ fontSize: 10, fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: 10 }}>
          Arquitectura Complementaria APEX Options (v2.0 / Doc v1.0)
        </div>
        <div style={{ color: '#888', fontSize: 13, lineHeight: 1.8 }}>
          Sistema 100% operativo con:
          <span style={{ color: '#FFF', fontWeight: 600 }}> Data Quality Gate (O-14)</span>,
          <span style={{ color: '#FFF', fontWeight: 600 }}> System Health & Kill Switch (O-15)</span>,
          <span style={{ color: '#FFF', fontWeight: 600 }}> Price Drift Revalidation (O-16)</span>,
          <span style={{ color: '#FFF', fontWeight: 600 }}> Net Greeks Analíticos</span>,
          <span style={{ color: '#FFF', fontWeight: 600 }}> EV Sensitivities & Robustness</span>,
          <span style={{ color: '#FFF', fontWeight: 600 }}> Replay Determinista</span>, y
          <span style={{ color: '#FFF', fontWeight: 600 }}> Libro Contrafactual</span>.
          Configuración avanzada en <Link href="/settings" style={{ color: '#AB47BC', fontWeight: 700 }}>Settings → Opciones (Secciones J a N)</Link>.
        </div>
      </div>
    </OptionsShell>
  )
}
