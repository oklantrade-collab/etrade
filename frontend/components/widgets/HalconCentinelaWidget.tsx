"use client"
import React from 'react'

interface HalconCentinelaWidgetProps {
  symbol: string
  halconData?: {
    score_final?: number
    semaforo?: string
    trading_paused?: boolean
  }
  position?: any
}

export default function HalconCentinelaWidget({ symbol, halconData, position }: HalconCentinelaWidgetProps) {
  const score = halconData?.score_final || 0
  const semaforo = halconData?.semaforo || 'VERDE'
  const isPaused = !!halconData?.trading_paused

  const getSemaforoStyle = (sem: string) => {
    switch (sem?.toUpperCase()) {
      case 'ROJO':
        return { color: '#FF4757', bg: 'rgba(255, 71, 87, 0.15)', border: '#FF4757', label: 'CIERRE TOTAL PROACTIVO' }
      case 'AMARILLO':
        return { color: '#F59E0B', bg: 'rgba(245, 158, 11, 0.15)', border: '#F59E0B', label: 'PRECAUCIÓN / CIERRE PARCIAL' }
      default:
        return { color: '#00C896', bg: 'rgba(0, 200, 150, 0.15)', border: '#00C896', label: 'SEGURO / MANTENER' }
    }
  }

  const semStyle = getSemaforoStyle(semaforo)

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
          <span style={{ fontSize: '18px' }}>🦅</span>
          <div>
            <h4 style={{ margin: 0, fontSize: '12px', fontWeight: 900, color: '#FFF', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              HALCÓN CENTINELA
            </h4>
            <span style={{ fontSize: '10px', color: '#64748B' }}>Defensa Proactiva & Oráculo</span>
          </div>
        </div>

        {/* Oraculo status */}
        <div style={{
          padding: '4px 8px',
          borderRadius: '6px',
          fontSize: '9px',
          fontWeight: 900,
          background: isPaused ? 'rgba(239, 68, 68, 0.2)' : 'rgba(0, 200, 150, 0.1)',
          color: isPaused ? '#EF4444' : '#00C896',
          border: `1px solid ${isPaused ? '#EF4444' : '#00C896'}`
        }}>
          {isPaused ? '🛑 ORÁCULO PAUSA' : '🟢 ORÁCULO CLEAR'}
        </div>
      </div>

      {/* Semaphore Bar */}
      <div style={{
        background: semStyle.bg,
        border: `1px solid ${semStyle.border}`,
        borderRadius: '10px',
        padding: '12px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{
            width: '10px', height: '10px', borderRadius: '50%',
            background: semStyle.color,
            boxShadow: `0 0 10px ${semStyle.color}`
          }} />
          <div>
            <div style={{ fontSize: '11px', fontWeight: 900, color: semStyle.color }}>
              SEMÁFORO {semaforo.toUpperCase()}
            </div>
            <div style={{ fontSize: '9px', color: '#CBD5E1', marginTop: '1px' }}>
              {semStyle.label}
            </div>
          </div>
        </div>

        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '8px', color: '#94A3B8', fontWeight: 700 }}>EXIT SCORE</div>
          <div style={{ fontSize: '16px', fontWeight: 900, color: '#FFF', fontFamily: 'monospace' }}>
            {score.toFixed(1)}
          </div>
        </div>
      </div>

      {/* GUÍA DE SEMÁFORO (Explicación de Colores) */}
      <div style={{
        background: 'rgba(0, 0, 0, 0.25)',
        padding: '10px 12px',
        borderRadius: '8px',
        border: '1px solid rgba(255, 255, 255, 0.05)',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        fontSize: '9px'
      }}>
        <div style={{ fontWeight: 800, color: '#94A3B8', textTransform: 'uppercase', fontSize: '8px', letterSpacing: '0.05em' }}>
          Significado del Semáforo Táctico:
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#00C896' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#00C896', display: 'inline-block' }} />
          <span><strong>VERDE (0-34 pts):</strong> Seguro / Mantener — Sin riesgo de giro. Posición en desarrollo.</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#F59E0B' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#F59E0B', display: 'inline-block' }} />
          <span><strong>AMARILLO (35-59 pts):</strong> Precaución — Divergencia RSI o compresión; asegurar parciales.</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#FF4757' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#FF4757', display: 'inline-block' }} />
          <span><strong>ROJO (60+ pts):</strong> Cierre Total Proactivo — Giro confirmado; salida inmediata.</span>
        </div>
      </div>

      {/* Position Protection Summary */}
      {position ? (
        <div style={{
          fontSize: '10px',
          color: '#94A3B8',
          display: 'flex',
          justifyContent: 'space-between',
          padding: '8px 12px',
          background: 'rgba(255, 255, 255, 0.02)',
          borderRadius: '8px'
        }}>
          <span>Posición Protegida:</span>
          <span style={{ color: '#FFF', fontWeight: 800 }}>
            {position.symbol} {position.side?.toUpperCase()} ({position.rule_code || 'MANUAL'})
          </span>
        </div>
      ) : (
        <div style={{ fontSize: '10px', color: '#64748B', fontStyle: 'italic', textAlign: 'center' }}>
          Sin posición activa para monitoreo de salida
        </div>
      )}
    </div>
  )
}
