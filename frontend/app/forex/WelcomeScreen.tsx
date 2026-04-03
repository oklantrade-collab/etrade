'use client'
import Link from 'next/link'

export default function ForexWelcomeScreen() {
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
        filter: 'drop-shadow(0 0 20px rgba(79,195,247,0.3))'
      }}>
        💱
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
          Forex — Sprint 3
        </h2>
        <p style={{
          color:     '#888',
          fontSize:  '15px',
          marginTop: '12px',
          maxWidth:  '440px',
          lineHeight: '1.6'
        }}>
          Conecta tu cuenta de <strong>IC Markets</strong> 
          para activar el trading algorítmico 
          en divisas con las mismas estrategias 
          que usas en Crypto.
        </p>
      </div>

      {/* PASOS DE ACTIVACIÓN */}
      <div style={{
        background:   'rgba(17, 24, 39, 0.4)',
        backdropFilter: 'blur(12px)',
        border:       '1px solid rgba(255, 255, 255, 0.04)',
        borderRadius: '16px',
        padding:      '32px',
        maxWidth:     '520px',
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
            title:'Obtener credenciales cTrader',
            detail:'openapi.ctrader.com → New App',
            status:'pending',
          },
          {
            step: 2,
            title:'Configurar variables de entorno',
            detail:'CTRADER_CLIENT_ID, SECRET, TOKEN',
            status:'pending',
          },
          {
            step: 3,
            title:'Probar conexión',
            detail:'python test_ctrader_connection.py',
            status:'pending',
          },
          {
            step: 4,
            title:'Activar en Settings → Forex',
            detail:'Asignar capital y activar pares',
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
              background:   'rgba(255,255,255,0.03)',
              border:       '1px solid rgba(255,255,255,0.06)',
              color:        '#555',
              fontSize:     '13px',
              fontWeight:   900,
              display:      'flex',
              alignItems:   'center',
              justifyContent:'center',
              flexShrink:   0,
            }}>
              {item.step}
            </div>
            <div>
              <div style={{
                color:    '#DDD',
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

      {/* BOTÓN IR A SETTINGS */}
      <Link href="/settings" style={{
        padding:      '14px 40px',
        borderRadius: '10px',
        background:   'rgba(79,195,247,0.12)',
        border:       '1px solid rgba(79,195,247,0.3)',
        color:        '#4FC3F7',
        fontSize:     '14px',
        fontWeight:   800,
        textDecoration:'none',
        cursor:       'pointer',
        transition:   'all 0.2s',
        textTransform: 'uppercase',
        letterSpacing: '0.05em'
      }}>
        ⚙️ Ir a Configuración Forex
      </Link>
    </div>
  )
}
