'use client'
import Link from 'next/link'

export default function StocksWelcomeScreen() {
  return (
    <div style={{
      display:        'flex',
      flexDirection:  'column',
      alignItems:     'center',
      justifyContent: 'center',
      minHeight:      '70vh',
      gap:            '32px',
    }}>

      <div style={{
        fontSize: '64px',
        filter: 'drop-shadow(0 0 20px rgba(34,197,94,0.3))'
      }}>
        📈
      </div>

      <div style={{ textAlign:'center' }}>
        <h2 style={{
          fontSize:  '32px',
          fontWeight:900,
          color:     '#FFF',
          margin:    0,
          fontStyle: 'italic',
          letterSpacing: '-0.03em'
        }}>
          Bolsa — Sprint 5
        </h2>
        <p style={{
          color:     '#888',
          fontSize:  '15px',
          marginTop: '12px',
          maxWidth:  '460px',
          lineHeight: '1.6'
        }}>
          Conecta <strong>Interactive Brokers</strong> y activa{' '}
          el trading algorítmico en acciones de EE.UU.{' '}
          con las mismas estrategias que usas en Crypto y Forex.
        </p>
      </div>

      {/* PASOS DE ACTIVACIÓN */}
      <div style={{
        background:   'rgba(17, 24, 39, 0.4)',
        backdropFilter: 'blur(12px)',
        border:       '1px solid rgba(255, 255, 255, 0.04)',
        borderRadius: '16px',
        padding:      '32px',
        maxWidth:     '560px',
        width:        '100%',
      }}>
        <div style={{
          color:         '#555',
          fontSize:      '11px',
          fontWeight:    900,
          letterSpacing: '0.2em',
          marginBottom:  '24px',
          textTransform: 'uppercase'
        }}>
          PASOS PARA ACTIVAR
        </div>

        {[
          {
            step: 1,
            title:'Ejecutar migración SQL',
            detail:'migration_025_stocks_module.sql en Supabase',
            status:'ready',
          },
          {
            step: 2,
            title:'Instalar dependencias',
            detail:'pip install yfinance (TA-Lib via ta ya instalado)',
            status:'ready',
          },
          {
            step: 3,
            title:'Configurar capital en Settings → Bolsa',
            detail:'Total capital, max % por trade, risk params',
            status:'pending',
          },
          {
            step: 4,
            title:'Instalar IB TWS (opcional — Sprint 7)',
            detail:'interactivebrokers.com → Paper Account',
            status:'future',
          },
          {
            step: 5,
            title:'Activar worker de Stocks',
            detail:'python stocks_scheduler.py (5m cycles en mercado)',
            status:'pending',
          },
        ].map(item => (
          <div key={item.step} style={{
            display:    'flex',
            gap:        '20px',
            alignItems: 'flex-start',
            marginBottom:'20px',
          }}>
            <div style={{
              width:        '32px',
              height:       '32px',
              borderRadius: '50%',
              background:   item.status === 'ready'
                ? 'rgba(34,197,94,0.15)'
                : item.status === 'future'
                  ? 'rgba(255,255,255,0.02)'
                  : 'rgba(255,255,255,0.03)',
              border:       `1px solid ${
                item.status === 'ready'
                  ? 'rgba(34,197,94,0.30)'
                  : 'rgba(255,255,255,0.06)'
              }`,
              color:        item.status === 'ready' ? '#22C55E' : '#555',
              fontSize:     '13px',
              fontWeight:   900,
              display:      'flex',
              alignItems:   'center',
              justifyContent:'center',
              flexShrink:   0,
            }}>
              {item.status === 'ready' ? '✓' : item.step}
            </div>
            <div>
              <div style={{
                color:    item.status === 'future' ? '#444' : '#DDD',
                fontSize: '14px',
                fontWeight:700,
              }}>
                {item.title}
              </div>
              <div style={{
                color:     '#666',
                fontSize:  '12px',
                marginTop: '4px',
                fontFamily:'monospace',
              }}>
                {item.detail}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* STACK INFO */}
      <div style={{
        display: 'flex',
        gap: '12px',
        flexWrap: 'wrap',
        justifyContent: 'center',
      }}>
        {['yfinance', 'IB TWS', 'TA-Lib', 'Strategy Engine v1.0'].map(tech => (
          <span key={tech} style={{
            padding: '6px 14px',
            borderRadius: '20px',
            background: 'rgba(255,255,255,0.03)',
            border: '1px solid rgba(255,255,255,0.06)',
            color: '#666',
            fontSize: '11px',
            fontWeight: 700,
          }}>
            {tech}
          </span>
        ))}
      </div>

      {/* BOTÓN IR A SETTINGS */}
      <Link href="/settings" style={{
        padding:      '14px 40px',
        borderRadius: '10px',
        background:   'rgba(34,197,94,0.12)',
        border:       '1px solid rgba(34,197,94,0.3)',
        color:        '#22C55E',
        fontSize:     '14px',
        fontWeight:   800,
        textDecoration:'none',
        cursor:       'pointer',
        transition:   'all 0.2s',
        textTransform: 'uppercase',
        letterSpacing: '0.05em'
      }}>
        ⚙️ Configurar Módulo Bolsa
      </Link>
    </div>
  )
}
