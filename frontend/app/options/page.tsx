"use client"
import Link from 'next/link'

export default function OptionsPage() {
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
        fontSize: '80px',
        filter: 'drop-shadow(0 0 30px rgba(171,71,188,0.3))',
        animation: 'pulse 3s ease-in-out infinite',
      }}>
        🎯
      </div>

      <div style={{ textAlign: 'center' }}>
        <h2 style={{
          fontSize:  '36px',
          fontWeight: 900,
          color:     '#FFF',
          margin:    0,
          fontStyle: 'italic',
          letterSpacing: '-0.03em',
        }}>
          Opciones
        </h2>
        <div style={{
          display: 'inline-block',
          marginTop: '12px',
          padding: '6px 20px',
          borderRadius: '20px',
          background: 'rgba(171,71,188,0.12)',
          border: '1px solid rgba(171,71,188,0.3)',
          color: '#AB47BC',
          fontSize: '11px',
          fontWeight: 900,
          textTransform: 'uppercase',
          letterSpacing: '0.15em',
        }}>
          Sprint 10+ — Coming Soon
        </div>
        <p style={{
          color: '#666',
          fontSize: '14px',
          marginTop: '20px',
          maxWidth: '500px',
          lineHeight: '1.7',
        }}>
          El módulo de Opciones (Derivados) se desarrollará después de
          completar y validar el módulo de Stocks (Sprints 5-9).
        </p>
      </div>

      {/* PREVIEW FEATURES */}
      <div style={{
        background: 'rgba(17, 24, 39, 0.4)',
        backdropFilter: 'blur(12px)',
        border: '1px solid rgba(255, 255, 255, 0.04)',
        borderRadius: '16px',
        padding: '32px',
        maxWidth: '480px',
        width: '100%',
      }}>
        <div style={{
          fontSize: '10px', fontWeight: 900, color: '#555',
          textTransform: 'uppercase', letterSpacing: '0.2em', marginBottom: '20px'
        }}>
          Funcionalidades Planeadas
        </div>

        {[
          { icon: '📊', title: 'Covered Call', desc: 'Generar ingreso sobre posiciones de acciones' },
          { icon: '🛡️', title: 'Cash-Secured Put', desc: 'Comprar acciones a descuento' },
          { icon: '📈', title: 'Long Call/Put', desc: 'Exposición apalancada con riesgo limitado' },
          { icon: '🧮', title: 'Greeks Calculator', desc: 'Delta, Theta, Vega, Gamma en tiempo real' },
          { icon: '🔗', title: 'Options Chain', desc: 'Visualización de cadena de opciones' },
        ].map((item, i) => (
          <div key={i} style={{
            display: 'flex', gap: '16px', alignItems: 'center',
            padding: '12px 0',
            borderBottom: i < 4 ? '1px solid rgba(255,255,255,0.03)' : 'none',
            opacity: 0.5,
          }}>
            <span style={{ fontSize: '20px' }}>{item.icon}</span>
            <div>
              <div style={{ color: '#AAA', fontSize: '13px', fontWeight: 700 }}>{item.title}</div>
              <div style={{ color: '#555', fontSize: '11px', marginTop: '2px' }}>{item.desc}</div>
            </div>
          </div>
        ))}
      </div>

      <Link href="/stocks/dashboard" style={{
        padding: '12px 32px',
        borderRadius: '8px',
        background: 'rgba(255,255,255,0.03)',
        border: '1px solid rgba(255,255,255,0.06)',
        color: '#888',
        fontSize: '13px',
        fontWeight: 700,
        textDecoration: 'none',
      }}>
        ← Volver a Stocks
      </Link>
    </div>
  )
}
