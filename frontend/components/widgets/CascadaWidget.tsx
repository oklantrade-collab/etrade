"use client"
import React from 'react'

interface CascadaWidgetProps {
  symbol: string
  position?: any
  radarSnapshot?: any
}

const LEVELS = [
  { level: 0, label: 'N0: Extremo (Rebote)', desc: 'Entrada en zona extrema' },
  { level: 1, label: 'N1: Cruce EMA 3/9', desc: '15m primer nivel de aceleración' },
  { level: 2, label: 'N2: Cruce EMA 9/20', desc: '15m confirmación intermedia' },
  { level: 3, label: 'N3: Cruce EMA 20/50', desc: '15m proyección de tendencia' },
  { level: 4, label: 'N4: Cruce EMA 50/200', desc: '15m alineación macro' },
  { level: 5, label: 'N5: Fibonacci Sucesivo', desc: 'Extensión máxima de bandas' },
]

export default function CascadaWidget({ symbol, position, radarSnapshot }: CascadaWidgetProps) {
  const currentLevel = position?.cascade_level !== undefined && position?.cascade_level !== null ? position.cascade_level : 0
  const isCascadeHold = !!position?.cascade_hold
  const pnlCurrent = parseFloat(position?.pnl_usd || position?.unrealized_pnl || position?.unrealized_pnl_usd || 0)
  const pnlPico = parseFloat(position?.pnl_pico || 0)
  const isReboteOrigin = position?.origen?.toUpperCase() === 'REBOTE' || position?.rule_code?.startsWith('AaReb') || position?.rule_code?.startsWith('BbReb')

  const floorPnl = pnlPico > 0 ? pnlPico * 0.5 : 0
  const pnlProgressPct = pnlPico > 0 ? Math.max(0, Math.min(100, (pnlCurrent / pnlPico) * 100)) : 0

  return (
    <div style={{
      background: 'rgba(15, 23, 42, 0.65)',
      backdropFilter: 'blur(12px)',
      border: '1px solid rgba(56, 189, 248, 0.2)',
      borderRadius: '16px',
      padding: '20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '16px',
      boxShadow: isCascadeHold ? '0 0 20px rgba(56, 189, 248, 0.15)' : 'none'
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '18px' }}>🌊</span>
          <div>
            <h4 style={{ margin: 0, fontSize: '12px', fontWeight: 900, color: '#38BDF8', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              CASCADA — Gestor en Extensión
            </h4>
            <span style={{ fontSize: '10px', color: '#64748B' }}>
              {isReboteOrigin ? 'Modo Activo (Origen: REBOTE)' : 'Monitoreo Pasivo (Modo Estándar)'}
            </span>
          </div>
        </div>
        
        {/* Cascade Hold Badge */}
        <div style={{
          padding: '4px 10px',
          borderRadius: '8px',
          fontSize: '9px',
          fontWeight: 900,
          background: isCascadeHold ? 'rgba(56, 189, 248, 0.2)' : 'rgba(255, 255, 255, 0.05)',
          color: isCascadeHold ? '#38BDF8' : '#64748B',
          border: `1px solid ${isCascadeHold ? '#38BDF8' : 'rgba(255,255,255,0.1)'}`,
          display: 'flex',
          alignItems: 'center',
          gap: '6px'
        }}>
          <span style={{
            width: '6px', height: '6px', borderRadius: '50%',
            background: isCascadeHold ? '#38BDF8' : '#64748B',
            boxShadow: isCascadeHold ? '0 0 8px #38BDF8' : 'none'
          }} />
          {isCascadeHold ? 'CASCADE HOLD: ACTIVO' : 'HOLD LIBRE'}
        </div>
      </div>

      {/* Waterfall Level Progress */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: '#94A3B8', fontWeight: 700 }}>
          <span>Nivel de Cascada Alcanzado:</span>
          <span style={{ color: '#38BDF8', fontWeight: 900 }}>NIVEL N{currentLevel}</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '6px' }}>
          {LEVELS.map((lvl) => {
            const isReached = currentLevel >= lvl.level
            const isCurrent = currentLevel === lvl.level
            return (
              <div key={lvl.level} style={{
                height: '32px',
                borderRadius: '6px',
                background: isReached
                  ? (isCurrent ? 'rgba(56, 189, 248, 0.4)' : 'rgba(56, 189, 248, 0.15)')
                  : 'rgba(255, 255, 255, 0.03)',
                border: `1px solid ${isCurrent ? '#38BDF8' : isReached ? 'rgba(56, 189, 248, 0.3)' : 'rgba(255, 255, 255, 0.05)'}`,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.3s ease'
              }}>
                <span style={{ fontSize: '11px', fontWeight: 900, color: isReached ? '#FFF' : '#475569' }}>
                  N{lvl.level}
                </span>
              </div>
            )
          })}
        </div>
        <div style={{ fontSize: '10px', color: '#64748B', fontStyle: 'italic' }}>
          {LEVELS[currentLevel]?.desc || 'Alineación de tendencia'}
        </div>
      </div>

      {/* Giveback Monitor (Floor Progress) */}
      {pnlPico > 0 && (
        <div style={{
          background: 'rgba(0, 0, 0, 0.25)',
          padding: '12px',
          borderRadius: '10px',
          border: '1px solid rgba(255, 255, 255, 0.05)'
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '10px', fontWeight: 800, color: '#94A3B8' }}>🛡️ Piso Giveback Dinámico:</span>
            <span style={{ fontSize: '11px', fontWeight: 900, color: pnlCurrent >= floorPnl ? '#00C896' : '#FF4757', fontFamily: 'monospace' }}>
              ${pnlCurrent.toFixed(2)} / Pico: ${pnlPico.toFixed(2)}
            </span>
          </div>

          <div style={{ width: '100%', height: '6px', background: 'rgba(255,255,255,0.05)', borderRadius: '3px', overflow: 'hidden', position: 'relative' }}>
            {/* 50% floor marker */}
            <div style={{ position: 'absolute', left: '50%', top: 0, width: '2px', height: '100%', background: '#EF4444', zIndex: 2 }} />
            <div style={{
              width: `${pnlProgressPct}%`,
              height: '100%',
              background: pnlProgressPct >= 50 ? 'linear-gradient(90deg, #F59E0B, #00C896)' : '#EF4444',
              transition: 'width 0.4s ease'
            }} />
          </div>

          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '8px', color: '#64748B', marginTop: '4px' }}>
            <span>$0.00</span>
            <span style={{ color: '#EF4444', fontWeight: 700 }}>Piso Cierre (50%): ${floorPnl.toFixed(2)}</span>
            <span>${pnlPico.toFixed(2)}</span>
          </div>
        </div>
      )}
    </div>
  )
}
