'use client';

import React from 'react';
import { useMarketBell } from '@/context/MarketBellContext';

export default function MarketBellModal() {
  const {
    enabled,
    toggleEnabled,
    volume,
    setVolume,
    nycTime,
    nextBell,
    testBell,
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
        backgroundColor: 'rgba(0, 0, 0, 0.75)',
        backdropFilter: 'blur(6px)',
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
          border: '1px solid rgba(255, 255, 255, 0.12)',
          borderRadius: '20px',
          width: '100%',
          maxWidth: '520px',
          padding: '28px',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.9), 0 0 35px rgba(34, 197, 94, 0.15)',
          color: '#FFF',
          fontFamily: 'Inter, system-ui, sans-serif',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '20px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ fontSize: '24px' }}>🔔</span>
              <h2 style={{ fontSize: '18px', fontWeight: 900, letterSpacing: '-0.02em', margin: 0, color: '#F8FAFC' }}>
                Campana Bursátil Automatizada
              </h2>
            </div>
            <p style={{ fontSize: '12px', color: '#94A3B8', marginTop: '4px', margin: 0 }}>
              Sincronizada con la campana oficial de Wall Street (NYSE / NASDAQ)
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
            background: 'linear-gradient(135deg, rgba(16, 24, 39, 0.8), rgba(22, 33, 54, 0.8))',
            border: '1px solid rgba(34, 197, 94, 0.25)',
            borderRadius: '14px',
            padding: '16px',
            marginBottom: '20px',
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
            padding: '14px 16px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: '12px',
            marginBottom: '12px',
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
              padding: '6px 16px',
              borderRadius: '20px',
              fontWeight: 900,
              fontSize: '12px',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
          >
            {enabled ? 'ACTIVADO 🔔' : 'SILENCIADO 🔕'}
          </button>
        </div>

        {/* Setting 2: Volume */}
        <div
          style={{
            padding: '14px 16px',
            background: 'rgba(255, 255, 255, 0.03)',
            borderRadius: '12px',
            marginBottom: '16px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
            <span style={{ fontSize: '13px', fontWeight: 800, color: '#F1F5F9' }}>Volumen de la Campana</span>
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

        {/* Test Buttons */}
        <div style={{ marginBottom: '16px' }}>
          <div style={{ fontSize: '11px', fontWeight: 800, color: '#64748B', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.08em' }}>
            Probar Sonido de Campana
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
            <button
              onClick={() => testBell('open')}
              style={{
                background: 'rgba(34, 197, 94, 0.12)',
                border: '1px solid rgba(34, 197, 94, 0.4)',
                color: '#4ADE80',
                padding: '10px 14px',
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
              <span>🔔</span> Probar Apertura
            </button>
            <button
              onClick={() => testBell('close')}
              style={{
                background: 'rgba(244, 63, 94, 0.12)',
                border: '1px solid rgba(244, 63, 94, 0.4)',
                color: '#FB7185',
                padding: '10px 14px',
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
              <span>🛎️</span> Probar Cierre
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
            {isUnlocked ? '✓ Sistema de audio listo en el navegador' : '⚠️ Haz clic abajo para autorizar audio'}
          </span>
          {!isUnlocked && (
            <button
              onClick={unlockAudio}
              style={{
                background: '#F59E0B',
                color: '#000',
                border: 'none',
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '10px',
                fontWeight: 900,
                cursor: 'pointer',
              }}
            >
              Activar
            </button>
          )}
        </div>

        {lastTriggered && (
          <div style={{ marginTop: '10px', fontSize: '11px', color: '#64748B', textAlign: 'center' }}>
            Última reproducción: <span style={{ color: '#94A3B8' }}>{lastTriggered}</span>
          </div>
        )}
      </div>
    </div>
  );
}
