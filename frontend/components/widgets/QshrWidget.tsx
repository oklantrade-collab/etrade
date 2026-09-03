'use client';
import React from 'react'

interface QshrWidgetProps {
  symbol: string
  position?: any
  snap?: any
}

export default function QshrWidget({ symbol, position, snap }: QshrWidgetProps) {
  const isPosOpen = !!position
  const isHedge = position?.rule_code === 'Bb33_QSHR_HEDGE' || position?.has_hedge
  const ruleCode = position?.rule_code || ''
  const adx = parseFloat(snap?.adx_15m || snap?.adx || 0)
  
  let stateLabel = 'MONITOREO NORMAL'
  let badgeColor = '#94A3B8'
  let badgeBg = 'rgba(148, 163, 184, 0.15)'
  let icon = '📊'

  if (isHedge) {
    stateLabel = 'COBERTURA ACTIVA (DELTA-0)'
    badgeColor = '#38BDF8'
    badgeBg = 'rgba(56, 189, 248, 0.2)'
    icon = '🛡️'
  } else if (ruleCode.includes('QSHR') || ruleCode.includes('Aa61')) {
    stateLabel = 'RIDE & CLOSE (EMA9 TRAIL)'
    badgeColor = '#00C896'
    badgeBg = 'rgba(0, 200, 150, 0.2)'
    icon = '🚀'
  } else if (adx < 18) {
    stateLabel = 'PINCH COMPRIMIENDO'
    badgeColor = '#F59E0B'
    badgeBg = 'rgba(245, 158, 11, 0.2)'
    icon = '🟡'
  }

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
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '18px' }}>⚛️</span>
          <div>
            <h4 style={{ margin: 0, fontSize: '12px', fontWeight: 900, color: '#FFF', letterSpacing: '0.1em', textTransform: 'uppercase' }}>
              QSHR v5 — Quantum HUD
            </h4>
            <span style={{ fontSize: '10px', color: '#64748B' }}>Squeeze, Hedge & Reversal ({symbol})</span>
          </div>
        </div>

        <div style={{
          padding: '4px 10px',
          borderRadius: '8px',
          fontSize: '9px',
          fontWeight: 900,
          background: badgeBg,
          color: badgeColor,
          border: `1px solid ${badgeColor}44`,
        }}>
          {icon} {stateLabel}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
        <div style={{
          background: 'rgba(255, 255, 255, 0.02)',
          border: '1px solid rgba(255, 255, 255, 0.06)',
          borderRadius: '8px',
          padding: '10px 8px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '4px'
        }}>
          <span style={{ fontSize: '9px', color: '#64748B', fontWeight: 700 }}>VELOCIDAD 5M</span>
          <span style={{ fontSize: '12px', fontWeight: 900, color: '#00C896' }}>
            V ≥ 2.5x
          </span>
          <span style={{ fontSize: '8px', color: '#475569' }}>Aceleracion</span>
        </div>

        <div style={{
          background: 'rgba(255, 255, 255, 0.02)',
          border: '1px solid rgba(255, 255, 255, 0.06)',
          borderRadius: '8px',
          padding: '10px 8px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '4px'
        }}>
          <span style={{ fontSize: '9px', color: '#64748B', fontWeight: 700 }}>SIPV CLIMAX</span>
          <span style={{ fontSize: '12px', fontWeight: 900, color: '#38BDF8' }}>
            15m Macro
          </span>
          <span style={{ fontSize: '8px', color: '#475569' }}>Presion/Vol</span>
        </div>

        <div style={{
          background: 'rgba(255, 255, 255, 0.02)',
          border: '1px solid rgba(255, 255, 255, 0.06)',
          borderRadius: '8px',
          padding: '10px 8px',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '4px'
        }}>
          <span style={{ fontSize: '9px', color: '#64748B', fontWeight: 700 }}>COBERTURA</span>
          <span style={{ fontSize: '12px', fontWeight: 900, color: isHedge ? '#38BDF8' : '#F59E0B' }}>
            1.5x Asym
          </span>
          <span style={{ fontSize: '8px', color: '#475569' }}>Delta Neutral</span>
        </div>
      </div>

      <div style={{
        background: 'rgba(0, 0, 0, 0.25)',
        padding: '8px 12px',
        borderRadius: '8px',
        fontSize: '9px',
        color: '#94A3B8',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        border: '1px solid rgba(255, 255, 255, 0.05)'
      }}>
        <span>Scale-Out: 50% SIPV + 50% EMA9</span>
        <span style={{ color: '#00C896', fontWeight: 800 }}>ADUANAS GATEWAY OK</span>
      </div>
    </div>
  )
}
