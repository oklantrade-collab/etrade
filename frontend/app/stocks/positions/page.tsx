"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

export default function StocksPositions() {
  const [positions, setPositions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [hasMounted, setHasMounted] = useState(false)
  const [selectedPos, setSelectedPos] = useState<any>(null)

  useEffect(() => {
    setHasMounted(true)
    fetchPositions()
    const interval = setInterval(fetchPositions, 10000)
    return () => clearInterval(interval)
  }, [])

  const fetchPositions = async () => {
    try {
      const res = await fetch('/api/v1/stocks/positions')
      const data = await res.json()
      setPositions(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  if (!hasMounted) return null

  const totalPnL = positions.reduce((acc, pos) => acc + (pos.unrealized_pnl || 0), 0)
  const totalCost = positions.reduce((acc, pos) => acc + (pos.total_cost || 0), 0)

  return (
    <div style={{ padding: '30px', background: '#080A0F', minHeight: '100vh', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      
      {/* MODAL DETALLE */}
      {selectedPos && (
        <div style={{ 
          position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', 
          background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(10px)', 
          zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' 
        }}>
          <div style={{ 
            background: '#12161F', width: '500px', borderRadius: '24px', 
            border: '1px solid rgba(255,255,255,0.1)', overflow: 'hidden',
            boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)'
          }}>
            <div style={{ padding: '30px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h2 style={{ fontSize: '22px', fontWeight: 900, margin: 0 }}>{selectedPos.ticker}</h2>
                <p style={{ color: '#00C896', fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', margin: '4px 0 0 0' }}>Detalle de Posición</p>
              </div>
              <button onClick={() => setSelectedPos(null)} style={{ background: 'rgba(255,255,255,0.05)', border: 'none', color: '#FFF', width: '32px', height: '32px', borderRadius: '50%', cursor: 'pointer', fontWeight: 900 }}>×</button>
            </div>
            
            <div style={{ padding: '30px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <DetailItem label="Empresa" val={selectedPos.company_name} color="#FFF" />
              <DetailItem label="Sector" val={selectedPos.sector} color="#FFF" />
              <DetailItem label="Fecha Compra" val={selectedPos.first_buy_at ? new Date(selectedPos.first_buy_at).toLocaleDateString() : '—'} color="#AAA" />
              <DetailItem label="Tipo Orden" val={selectedPos.order_type} color="#00C896" />
              <DetailItem label="Precio Entrada" val={`$${selectedPos.avg_price?.toFixed(2)}`} color="#FFF" />
              <DetailItem label="Cantidad" val={selectedPos.shares} color="#FFF" />
              <DetailItem label="Stop Loss (SL)" val={selectedPos.sl_price ? `$${selectedPos.sl_price}` : '—'} color="#FF4757" />
              <DetailItem label="Take Profit (TP)" val={selectedPos.tp_price ? `$${selectedPos.tp_price}` : '—'} color="#00C896" />
              <DetailItem label="Inversión" val={`$${selectedPos.total_cost?.toLocaleString()}`} color="#AAA" />
              
              <div style={{ gridColumn: 'span 2', background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '16px', marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                   <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>P&L No Realizado</p>
                   <p style={{ margin: 0, fontSize: '24px', fontWeight: 900, color: (selectedPos.unrealized_pnl || 0) >= 0 ? '#00C896' : '#FF4757' }}>
                     {(selectedPos.unrealized_pnl || 0) >= 0 ? '+' : ''}${(selectedPos.unrealized_pnl || 0).toFixed(2)}
                   </p>
                </div>
                <div style={{ textAlign: 'right' }}>
                   <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>Retorno (ROI)</p>
                   <p style={{ margin: 0, fontSize: '20px', fontWeight: 900, color: (selectedPos.unrealized_pnl_pct || 0) >= 0 ? '#00C896' : '#FF4757' }}>
                     {(selectedPos.unrealized_pnl_pct || 0) >= 0 ? '+' : ''}{(selectedPos.unrealized_pnl_pct || 0).toFixed(2)}%
                   </p>
                </div>
              </div>
            </div>
            
            <div style={{ padding: '20px 30px', background: 'rgba(255,255,255,0.02)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
               <button onClick={() => setSelectedPos(null)} style={{ width: '100%', padding: '14px', borderRadius: '12px', border: 'none', background: '#00C896', color: '#000', fontWeight: 900, cursor: 'pointer', fontSize: '13px' }}>CERRAR DETALLES</button>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 900, margin: 0, letterSpacing: '-0.02em' }}>💼 Portafolio Stocks</h1>
          <p style={{ color: '#666', fontSize: '14px', marginTop: '5px' }}>Gestión de posiciones industriales v5.0</p>
        </div>
        <div style={{ display: 'flex', gap: '20px' }}>
          <div style={{ textAlign: 'right' }}>
            <p style={{ fontSize: '11px', color: '#666', textTransform: 'uppercase', fontWeight: 800, margin: 0 }}>Costo Total</p>
            <p style={{ fontSize: '18px', fontWeight: 900, margin: 0 }}>${totalCost.toLocaleString(undefined, { minimumFractionDigits: 2 })}</p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <p style={{ fontSize: '11px', color: '#666', textTransform: 'uppercase', fontWeight: 800, margin: 0 }}>PnL No Realizado</p>
            <p style={{ fontSize: '18px', fontWeight: 900, margin: 0, color: totalPnL >= 0 ? '#00C896' : '#FF4757' }}>
              {totalPnL >= 0 ? '+' : ''}${totalPnL.toLocaleString(undefined, { minimumFractionDigits: 2 })}
            </p>
          </div>
        </div>
      </div>

      <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '100px 100px 105px 70px 95px 95px 95px 50px 120px 115px', 
          padding: '16px 24px', 
          background: 'rgba(255,255,255,0.03)',
          fontSize: '10px', 
          fontWeight: 900, 
          color: '#555', 
          textTransform: 'uppercase',
          letterSpacing: '0.1em'
        }}>
          <span>Ticker</span>
          <span>Grupo</span>
          <span>Fecha</span>
          <span>Shares</span>
          <span>Avg</span>
          <span>Actual</span>
          <span>Costo</span>
          <span>DCA</span>
          <span style={{ textAlign: 'right' }}>PnL (%)</span>
          <span style={{ textAlign: 'right' }}>Acción</span>
        </div>

        {loading && <div style={{ padding: '60px', textAlign: 'center', color: '#444' }}>Cargando portafolio...</div>}
        {!loading && positions.length === 0 && <div style={{ padding: '60px', textAlign: 'center', color: '#444' }}>No hay posiciones abiertas en este momento.</div>}
        
        {!loading && positions.map((pos, i) => (
          <div key={pos.id} style={{ 
            display: 'grid', 
            gridTemplateColumns: '100px 100px 105px 70px 95px 95px 95px 50px 120px 115px', 
            padding: '18px 24px', 
            borderBottom: '1px solid rgba(255,255,255,0.02)',
            alignItems: 'center',
            background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)'
          }}>
            <span style={{ fontWeight: 900, fontSize: '15px' }}>{pos.ticker}</span>
            <span style={{ 
              fontSize: '9px', 
              fontWeight: 800, 
              color: pos.group_name === 'inversiones_pro' ? '#4FC3F7' : '#FF8A65',
              background: pos.group_name === 'inversiones_pro' ? 'rgba(79,195,247,0.1)' : 'rgba(255,138,101,0.1)',
              padding: '4px 6px',
              borderRadius: '4px',
              display: 'inline-block',
              width: 'fit-content',
              textTransform: 'uppercase'
            }}>
              {pos.group_name === 'inversiones_pro' ? 'PRO' : 'HOT'}
            </span>
            <span style={{ fontSize: '11px', color: '#666' }}>
                {pos.first_buy_at ? new Date(pos.first_buy_at).toLocaleDateString() : '—'}
            </span>
            <span style={{ fontWeight: 700 }}>{pos.shares}</span>
            <span style={{ color: '#AAA', fontSize: '13px' }}>${pos.avg_price?.toFixed(2)}</span>
            <span style={{ fontWeight: 700, fontSize: '13px' }}>${pos.current_price?.toFixed(2)}</span>
            <span style={{ color: '#AAA', fontSize: '13px' }}>${pos.total_cost?.toFixed(2)}</span>
            <span style={{ color: pos.dca_count > 0 ? '#CE93D8' : '#444', fontWeight: 800, textAlign: 'center' }}>
              {pos.dca_count > 0 ? `×${pos.dca_count}` : '—'}
            </span>
            <div style={{ textAlign: 'right' }}>
              <p style={{ margin: 0, fontWeight: 900, color: (pos.unrealized_pnl || 0) > 0 ? '#00C896' : (pos.unrealized_pnl || 0) < 0 ? '#FF4757' : '#AAA' }}>
                {(pos.unrealized_pnl || 0) > 0 ? '+' : ''}${(pos.unrealized_pnl || 0).toFixed(2)}
              </p>
              <p style={{ margin: 0, fontSize: '11px', color: (pos.unrealized_pnl_pct || 0) > 0 ? '#00C896' : (pos.unrealized_pnl_pct || 0) < 0 ? '#FF4757' : '#AAA', opacity: 0.8 }}>
                {(pos.unrealized_pnl_pct || 0) > 0 ? '+' : ''}{(pos.unrealized_pnl_pct || 0).toFixed(2)}%
              </p>
            </div>
            <div style={{ textAlign: 'right' }}>
               <button onClick={() => setSelectedPos(pos)} style={{ background: 'rgba(0,200,150,0.1)', border: '1px solid rgba(0,200,150,0.2)', color: '#00C896', fontSize: '10px', fontWeight: 900, padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', textTransform: 'uppercase' }}>Detalle</button>
            </div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '30px' }}>
        <Link href="/stocks/opportunities" style={{ color: '#00C896', textDecoration: 'none', fontWeight: 800, fontSize: '12px' }}>
          ← IR AL SCANNER DE OPORTUNIDADES
        </Link>
      </div>
    </div>
  )
}

function DetailItem({ label, val, color }: any) {
  return (
    <div>
      <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</p>
      <p style={{ margin: '4px 0 0 0', fontSize: '14px', fontWeight: 700, color }}>{val || '—'}</p>
    </div>
  )
}
