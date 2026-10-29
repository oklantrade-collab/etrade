'use client';

import React from 'react';
import { useMarketBell } from '@/context/MarketBellContext';

export default function MarketBellButton({ compact = false }: { compact?: boolean }) {
  const { enabled, setShowModal, nextBell, nycTime, isUnlocked, unlockAudio } = useMarketBell();

  const handleClick = () => {
    if (!isUnlocked) {
      unlockAudio();
    }
    setShowModal(true);
  };

  return (
    <button
      onClick={handleClick}
      title={`Campana Bursátil Thinkorswim: ${enabled ? 'Activada' : 'Silenciada'} • Audio: ${isUnlocked ? 'Listo' : 'Requiere Clic'} • NYC: ${nycTime.timeStr} ET • Próxima: ${nextBell.countdownStr}`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontSize: '10px',
        fontWeight: 900,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
        background: enabled ? 'rgba(34, 197, 94, 0.12)' : 'rgba(239, 68, 68, 0.12)',
        color: enabled ? '#4ADE80' : '#F87171',
        border: `1px solid ${enabled ? 'rgba(34, 197, 94, 0.35)' : 'rgba(239, 68, 68, 0.35)'}`,
        padding: '2px 8px',
        borderRadius: '6px',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
      }}
    >
      <span style={{ fontSize: '11px' }}>{enabled ? '🔔' : '🔕'}</span>
      <span>
        {compact
          ? (enabled ? 'CAMPANA ON' : 'CAMPANA OFF')
          : `CAMPANA ${enabled ? 'ON' : 'OFF'} (${nextBell.countdownStr})`
        }
      </span>
      {!isUnlocked && (
        <span 
          title="Haz clic para autorizar audio en el navegador" 
          style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#F59E0B', display: 'inline-block' }}
        />
      )}
    </button>
  );
}
