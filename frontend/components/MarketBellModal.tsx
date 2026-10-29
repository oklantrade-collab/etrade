'use client';

import React from 'react';
import { useMarketBell } from '@/context/MarketBellContext';
import { BellSoundProfile } from '@/lib/audio/marketBell';

export default function MarketBellModal() {
  const {
    enabled,
    toggleEnabled,
    volume,
    setVolume,
    soundProfile,
    setSoundProfile,
    availableSounds,
    nycTime,
    nextBell,
    testBell,
    playOrderSound,
    isUnlocked,
    unlockAudio,
    lastTriggered,
    showModal,
    setShowModal,
  } = useMarketBell();

  if (!showModal) return null;

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.78)',
        backdropFilter: 'blur(8px)',
        zIndex: 99999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
      onClick={() => setShowModal(false)}
    >
      <div
        style={{
          background: '#0d111a',
          border: '1px solid rgba(255, 255, 255, 0.14)',
          borderRadius: '20px',
          width: '100%',
          maxWidth: '540px',
          padding: '26px',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.95), 0 0 35px rgba(34, 197, 94, 0.18)',
          color: '#FFF',
          fontFamily: 'Inter, system-ui, sans-serif',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '18px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '24px' }}>🔔</span>
              <h2 style={{ fontSize: '18px', fontWeight: 900, letterSpacing: '-0.02em', margin: 0, color: '#F8FAFC' }}>
                Campana Bursátil Automatizada
              </h2>
            </div>
            <p style={{ fontSize: '12px', color: '#94A3B8', marginTop: '4px', margin: 0 }}>
              Audio auténtico de <strong>Thinkorswim (Charles Schwab)</strong> sincronizado con Wall Street (NYSE / NASDAQ)
            </p>
          </div>
          <button
            onClick={() => setShowModal(false)}
            style={{
              background: 'rgba(255, 255, 255, 0.06)',
              border: 'none',
              borderRadius: '50%',
              width: '32px',
              height: '32px',
              color: '#94A3B8',
              fontSize: '16px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            ✕
          </button>
        </div>

        {/* Live NYC Time & Status Card */}
        <div
          style={{
            background: 'linear-gradient(135deg, rgba(16, 24, 39, 0.85), rgba(22, 33, 54, 0.85))',
            border: '1px solid rgba(34, 197, 94, 0.25)',
            borderRadius: '14px',
            padding: '16px',
            marginBottom: '16px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.12em', color: '#22C55E', fontWeight: 900 }}>
              HORA OFICIAL WALL STREET (NYC)
            </div>
            <div style={{ fontSize: '24px', fontWeight: 900, fontFamily: 'monospace', color: '#FFF', marginTop: '2px' }}>
              {nycTime.timeStr} <span style={{ fontSize: '12px', color: '#64748B' }}>ET</span>
            </div>
            <div style={{ fontSize: '11px', color: '#94A3B8', marginTop: '2px' }}>
              {nycTime.dateStr} • {nextBell.statusText}
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.1em', color: '#94A3B8', fontWeight: 800 }}>
              PRÓXIMA CAMPANA
            </div>
            <div
              style={{
                fontSize: '13px',
                fontWeight: 900,
                color: nextBell.type === 'open' ? '#22C55E' : '#F59E0B',
                marginTop: '4px',
                background: nextBell.type === 'open' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(245, 158, 11, 0.15)',
                padding: '4px 10px',
                borderRadius: '8px',
                display: 'inline-block',
              }}
            >
              {nextBell.type === 'open' ? 'Apertura (09:30 ET)' : 'Cierre (16:00 ET)'}
            </div>
            <div style={{ fontSize: '11px', color: '#CBD5E1', marginTop: '4px', fontFamily: 'monospace' }}>
              {nextBell.countdownStr}
            </div>
          </div>
        </div>

        {/* Setting 1: Toggle sound */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '12px 14px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: '12px',
            marginBottom: '10px',
          }}
        >
          <div>
            <div style={{ fontSize: '13px', fontWeight: 800, color: '#F1F5F9' }}>
              Sonido Automático de Campana
            </div>
            <div style={{ fontSize: '11px', color: '#94A3B8', marginTop: '2px' }}>
              Suena automáticamente al abrir (09:30) y cerrar (16:00) la sesión diaria.
            </div>
          </div>
          <button
            onClick={toggleEnabled}
            style={{
              background: enabled ? '#22C55E' : 'rgba(255, 255, 255, 0.1)',
              color: enabled ? '#000' : '#94A3B8',
              border: 'none',
              padding: '6px 14px',
              borderRadius: '20px',
              fontWeight: 900,
              fontSize: '11px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
          >
            {enabled ? 'ACTIVADO 🔔' : 'SILENCIADO 🔕'}
          </button>
        </div>

        {/* Setting 2: Thinkorswim Sound Profile Selector */}
        <div
          style={{
            padding: '12px 14px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: '12px',
            marginBottom: '10px',
          }}
        >
          <div style={{ fontSize: '13px', fontWeight: 800, color: '#F1F5F9', marginBottom: '8px' }}>
            Tono de Campana (Colección Thinkorswim)
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {availableSounds.map((s) => {
              const isSelected = soundProfile === s.id;
              return (
                <div
                  key={s.id}
                  onClick={() => setSoundProfile(s.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    background: isSelected ? 'rgba(34, 197, 94, 0.12)' : 'rgba(255, 255, 255, 0.02)',
                    border: `1px solid ${isSelected ? 'rgba(34, 197, 94, 0.45)' : 'rgba(255, 255, 255, 0.06)'}`,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ color: isSelected ? '#22C55E' : '#64748B', fontSize: '13px' }}>
                      {isSelected ? '●' : '○'}
                    </span>
                    <div>
                      <div style={{ fontSize: '12px', fontWeight: isSelected ? 800 : 600, color: isSelected ? '#FFF' : '#CBD5E1' }}>
                        {s.name}
                      </div>
                      <div style={{ fontSize: '10px', color: '#94A3B8' }}>
                        {s.description}
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      testBell('open', s.id);
                    }}
                    title="Escuchar muestra"
                    style={{
                      background: 'rgba(255, 255, 255, 0.08)',
                      border: 'none',
                      color: '#4ADE80',
                      borderRadius: '6px',
                      padding: '4px 8px',
                      fontSize: '11px',
                      cursor: 'pointer',
                    }}
                  >
                    ▶ Probar
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {/* Setting 3: Volume Slider */}
        <div
          style={{
            padding: '12px 14px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: '12px',
            marginBottom: '14px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '13px', fontWeight: 800, color: '#F1F5F9' }}>Volumen de Reproducción</span>
            <span style={{ fontSize: '12px', fontWeight: 800, fontFamily: 'monospace', color: '#22C55E' }}>
              {Math.round(volume * 100)}%
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={volume}
            onChange={(e) => setVolume(parseFloat(e.target.value))}
            style={{
              width: '100%',
              accentColor: '#22C55E',
              cursor: 'pointer',
            }}
          />
        </div>

        {/* Test Buttons for Bells and Thinkorswim Orders */}
        <div style={{ marginBottom: '14px' }}>
          <div style={{ fontSize: '11px', fontWeight: 800, color: '#64748B', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.08em' }}>
            Probar Campanas Oficiales (Wall Street)
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '10px' }}>
            <button
              onClick={() => testBell('open')}
              style={{
                background: 'rgba(34, 197, 94, 0.12)',
                border: '1px solid rgba(34, 197, 94, 0.4)',
                color: '#4ADE80',
                padding: '9px 12px',
                borderRadius: '10px',
                fontSize: '12px',
                fontWeight: 800,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                transition: 'all 0.15s ease',
              }}
            >
              <span>🔔</span> Probar Apertura (TOS)
            </button>
            <button
              onClick={() => testBell('close')}
              style={{
                background: 'rgba(244, 63, 94, 0.12)',
                border: '1px solid rgba(244, 63, 94, 0.4)',
                color: '#FB7185',
                padding: '9px 12px',
                borderRadius: '10px',
                fontSize: '12px',
                fontWeight: 800,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                transition: 'all 0.15s ease',
              }}
            >
              <span>🛎️</span> Probar Cierre (TOS)
            </button>
          </div>

          <div style={{ fontSize: '11px', fontWeight: 800, color: '#64748B', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.08em' }}>
            Sonidos de Ejecución Broker (Thinkorswim)
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <button
              onClick={() => playOrderSound('buy', { symbol: 'AAPL', shares: 50, price: 232.50 })}
              style={{
                background: 'rgba(6, 182, 212, 0.12)',
                border: '1px solid rgba(6, 182, 212, 0.4)',
                color: '#22D3EE',
                padding: '9px 12px',
                borderRadius: '10px',
                fontSize: '12px',
                fontWeight: 800,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                transition: 'all 0.15s ease',
              }}
            >
              <span>🛒</span> Compra (Ding)
            </button>
            <button
              onClick={() => playOrderSound('close', { symbol: 'AAPL', shares: 50, price: 236.80 })}
              style={{
                background: 'rgba(245, 158, 11, 0.12)',
                border: '1px solid rgba(245, 158, 11, 0.4)',
                color: '#FBBF24',
                padding: '9px 12px',
                borderRadius: '10px',
                fontSize: '12px',
                fontWeight: 800,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '6px',
                transition: 'all 0.15s ease',
              }}
            >
              <span>💰</span> Venta / Cierre (Chimes)
            </button>
          </div>
        </div>

        {/* Audio Autoplay State Notice */}
        <div
          style={{
            fontSize: '11px',
            color: isUnlocked ? '#22C55E' : '#F59E0B',
            background: isUnlocked ? 'rgba(34, 197, 94, 0.08)' : 'rgba(245, 158, 11, 0.08)',
            border: `1px solid ${isUnlocked ? 'rgba(34, 197, 94, 0.2)' : 'rgba(245, 158, 11, 0.2)'}`,
            padding: '8px 12px',
            borderRadius: '8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span>
            {isUnlocked 
              ? '✓ Audio listo y autorizado por el navegador' 
              : '⚠️ El navegador requiere interacción previa para reproducir sonido'
            }
          </span>
          {!isUnlocked && (
            <button
              onClick={unlockAudio}
              style={{
                background: '#F59E0B',
                color: '#000',
                border: 'none',
                padding: '3px 10px',
                borderRadius: '5px',
                fontSize: '10px',
                fontWeight: 900,
                cursor: 'pointer',
              }}
            >
              Autorizar Audio
            </button>
          )}
        </div>

        {lastTriggered && (
          <div style={{ marginTop: '10px', fontSize: '11px', color: '#64748B', textAlign: 'center' }}>
            Última campana: <span style={{ color: '#94A3B8' }}>{lastTriggered}</span>
          </div>
        )}
      </div>
    </div>
  );
}
