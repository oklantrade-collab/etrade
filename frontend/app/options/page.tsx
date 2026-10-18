'use client'
import { useEffect, useState } from 'react'
import { OptionsShell, optCard, useOptionsStatus } from '@/components/options/OptionsShell'

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{ ...optCard, padding: 18 }}>
      <div style={{ fontSize: 10, fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.15em' }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 900, color: '#FFF', marginTop: 6 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: '#666', marginTop: 4 }}>{sub}</div>}
    </div>
  )
}

export default function OptionsDashboard() {
  const { status, error } = useOptionsStatus()
  const [g1, setG1] = useState<any>(null)
  useEffect(() => { fetch('/api/v1/options/g1').then(r => r.ok ? r.json() : null).then(setG1).catch(() => {}) }, [])
  const caps = status?.hard_caps
  return (
    <OptionsShell title="Options Dashboard" active="/options">
      {error && <div style={{ ...optCard, color: '#EF5350', fontSize: 13 }}>No se pudo leer el estado del módulo (API {error}).</div>}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
        <Kpi label="Módulo" value={status ? (status.module_enabled ? 'ACTIVO' : 'DESACTIVADO') : '…'} sub="OPTIONS_ENABLED (backend)" />
        <Kpi label="Modo" value="PAPER" sub={status?.execution_mode_ok === false ? '⚠ OPTIONS_EXECUTION_MODE inválido' : 'Sin órdenes reales por diseño'} />
        <Kpi label="Techo riesgo/operación" value={caps ? `$${caps.max_risk_per_trade_usd}` : '…'} sub="Editable en Settings hasta este techo" />
        <Kpi label="Techo riesgo abierto" value={caps ? `$${caps.max_open_risk_usd}` : '…'} />
        <Kpi label="Gate G1" value={g1?.verdict ?? '…'} sub={g1 ? `${g1.sessions_measured}/${g1.required_sessions} sesiones medidas · ${g1.pct_passed}% cumplen (req. ${g1.required_pct}%)` : undefined} />
      </div>
      <div style={optCard}>
        <div style={{ fontSize: 10, fontWeight: 900, color: '#555', textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: 10 }}>Estado de construcción</div>
        <div style={{ color: '#888', fontSize: 13, lineHeight: 1.8 }}>
          Fase actual: <b style={{ color: '#26A69A' }}>Sprints 1–7 Completados</b>. Módulo de Paper Trading 100% operativo con valoración Black-Scholes, ADUANA, Options Score, Selector de Cartera, Paper Trading y Gates G1–G3.
          Configuración y techos de riesgo en{' '}<a href="/settings" style={{ color: '#AB47BC' }}>Settings → Opciones</a>.
        </div>
      </div>
    </OptionsShell>
  )
}
