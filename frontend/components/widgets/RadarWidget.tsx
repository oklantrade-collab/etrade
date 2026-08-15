"use client"
import React from 'react'

interface RadarWidgetProps {
  symbol: string
  radarSnapshot?: any
}

export default function RadarWidget({ symbol, radarSnapshot }: RadarWidgetProps) {
  const snap = radarSnapshot || {}
  const status = snap.status || 'sin_datos'

  const slopeEma3 = snap.pendiente_EMA3 || 'sin_datos'
  const slopeEma9 = snap.pendiente_EMA9 || 'sin_datos'
  const slopeEma20 = snap.pendiente_EMA20 || 'sin_datos'
  
  const slopeValEma3 = snap.slope_ema3_val !== undefined ? snap.slope_ema3_val : 0
  const slopeValEma20 = snap.slope_ema20_val !== undefined ? snap.slope_ema20_val : 0

  const matrix = snap.slope_matrix || {}
  const matrixStatus = matrix.status || 'sin_datos'
  const matrixDetail = matrix.detail || 'Evaluando condiciones...'

  const adxRegime = snap.regimen_ADX || 'moderate'
  const localRegime = snap.regimen_local_15m || 'neutral'
  const squeezeActive = !!snap.squeeze_activo
  const fibZone = snap.fibonacci_zone !== undefined ? snap.fibonacci_zone : 0

  const getSlopeColor = (slope: string) => {
    if (slope === 'ascending') return '#00C896'
    if (slope === 'descending') return '#FF4757'
    if (slope === 'lateral') return '#F59E0B'
    return '#64748B'
  }

  const getMatrixBadge = (mStatus: string) => {
    if (mStatus.includes('strong_trend')) {
      return { label: 'TENDENCIA FUERTE', bg: 'rgba(0, 200, 150, 0.15)', color: '#00C896', border: '#00C896' }
    }
    if (mStatus.includes('pullback')) {
      return { label: 'RUIDO / PULLBACK', bg: 'rgba(245, 158, 11, 0.15)', color: '#F59E0B', border: '#F59E0B' }
    }
    if (mStatus.includes('real_reversal')) {
      return { label: 'REVERSIÓN REAL PROBABLE', bg: 'rgba(239, 68, 68, 0.15)', color: '#EF4444', border: '#EF4444' }
    }
    return { label: 'TRANSICIÓN', bg: 'rgba(100, 116, 139, 0.15)', color: '#94A3B8', border: '#64748B' }
  }

  const matrixBadge = getMatrixBadge(matrixStatus)

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.65)',
      backdropFilter: 'blur(12px)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      borderRadius: '16px',
      padding: '20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '14px'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '18px' }}>📡</span>
          <div>
            <h4 style={{ margin: 0, fontSize: '12px', fontWeight: 900, color: '#FFF', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              RADAR — Bus de Señales
            </h4>
            <span style={{ fontSize: '10px', color: '#64748B' }}>15m Momento y Tendencia ({symbol})</span>
          </div>
        </div>

        <div style={{
          padding: '4px 10px',
          borderRadius: '8px',
          fontSize: '9px',
          fontWeight: 900,
          background: matrixBadge.bg,
          color: matrixBadge.color,
          border: `1px solid ${matrixBadge.border}`
        }}>
          {matrixBadge.label}
        </div>
      </div>

      {/* Slope Matrix Status */}
      <div style={{
        background: 'rgba(0, 0, 0, 0.25)',
        padding: '10px 14px',
        borderRadius: '10px',
        fontSize: '10px',
        color: '#CBD5E1',
        border: '1px solid rgba(255, 255, 255, 0.05)'
      }}>
        <div style={{ fontWeight: 800, color: '#94A3B8', marginBottom: '2px' }}>Análisis Combinado EMA3 × EMA20:</div>
        <div>{matrixDetail}</div>
      </div>

      {/* Slopes 3-Column Display */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
        <SlopeBox label="EMA 3 (Velocidad)" slope={slopeEma3} value={slopeValEma3} color={getSlopeColor(slopeEma3)} />
        <SlopeBox label="EMA 9 (Puente)" slope={slopeEma9} value={snap.slope_ema9_val} color={getSlopeColor(slopeEma9)} />
        <SlopeBox label="EMA 20 (Tendencia)" slope={slopeEma20} value={slopeValEma20} color={getSlopeColor(slopeEma20)} />
      </div>

      {/* Indicators Summary Footer */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '6px',
        paddingTop: '10px',
        borderTop: '1px solid rgba(255, 255, 255, 0.05)',
        fontSize: '9px',
        textAlign: 'center'
      }}>
        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '6px', borderRadius: '6px' }}>
          <div style={{ color: '#64748B', fontWeight: 700 }}>RÉGIMEN ADX</div>
          <div style={{ color: '#FFF', fontWeight: 900, textTransform: 'uppercase', marginTop: '2px' }}>{adxRegime}</div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '6px', borderRadius: '6px' }}>
          <div style={{ color: '#64748B', fontWeight: 700 }}>SQUEEZE BB</div>
          <div style={{ color: squeezeActive ? '#F59E0B' : '#64748B', fontWeight: 900, marginTop: '2px' }}>
            {squeezeActive ? '⚡ ACTIVO' : 'INACTIVO'}
          </div>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.02)', padding: '6px', borderRadius: '6px' }}>
          <div style={{ color: '#64748B', fontWeight: 700 }}>ZONA FIBONACCI</div>
          <div style={{ color: fibZone !== 0 ? '#38BDF8' : '#FFF', fontWeight: 900, marginTop: '2px' }}>
            {fibZone > 0 ? `+${fibZone} (UPPER)` : fibZone < 0 ? `${fibZone} (LOWER)` : '0 (CENTRAL)'}
          </div>
        </div>
      </div>
    </div>
  )
}

function SlopeBox({ label, slope, value, color }: any) {
  return (
    <div style={{
      background: 'rgba(255, 255, 255, 0.02)',
      border: `1px solid ${color}33`,
      borderRadius: '8px',
      padding: '10px 8px',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: '4px'
    }}>
      <span style={{ fontSize: '9px', color: '#64748B', fontWeight: 700 }}>{label}</span>
      <span style={{ fontSize: '11px', fontWeight: 900, color: color, textTransform: 'uppercase' }}>
        {slope === 'ascending' ? '▲ ASC' : slope === 'descending' ? '▼ DESC' : slope === 'lateral' ? '► LAT' : '—'}
      </span>
      {value !== undefined && (
        <span style={{ fontSize: '8px', color: '#475569', fontFamily: 'monospace' }}>
          {typeof value === 'number' ? `${value > 0 ? '+' : ''}${value.toFixed(2)}` : ''}
        </span>
      )}
    </div>
  )
}
