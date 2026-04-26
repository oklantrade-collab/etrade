"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

export default function StocksPositions() {
  const [positions, setPositions] = useState<any[]>([])
  const [closedPositions, setClosedPositions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [hasMounted, setHasMounted] = useState(false)
  const [selectedPos, setSelectedPos] = useState<any>(null)
  const [tab, setTab] = useState<'open' | 'closed'>('open')

  useEffect(() => {
    setHasMounted(true)
    fetchData()
    const interval = setInterval(fetchData, 10000)
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const [openRes, closedRes] = await Promise.all([
        fetch('/api/v1/stocks/positions'),
        fetch('/api/v1/stocks/journal?limit=50')
      ])
      
      if (!openRes.ok || !closedRes.ok) throw new Error('API Error')

      const openData = await openRes.json()
      const closedData = await closedRes.json()
      
      setPositions(Array.isArray(openData.positions) ? openData.positions : [])
      setClosedPositions(Array.isArray(closedData) ? closedData : [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const handleDelete = async (posId: string, ticker: string) => {
    if (!confirm(`¿Estás seguro de eliminar la posición de ${ticker} manualmente?`)) return
    
    try {
      const res = await fetch(`/api/v1/stocks/positions/${posId}`, { method: 'DELETE' })
      if (res.ok) {
        setPositions(prev => prev.filter(p => p.id !== posId))
        alert(`Posición de ${ticker} cerrada manualmente.`)
        fetchData()
      } else {
        alert('Error al eliminar la posición.')
      }
    } catch (err) {
      alert('Error de conexión.')
    }
  }

  if (!hasMounted) return null

  const totalPnL = positions.reduce((acc, pos) => acc + (pos.unrealized_pnl || 0), 0)
  const totalCost = positions.reduce((acc, pos) => acc + (pos.total_cost || 0), 0)
  const totalShares = positions.reduce((acc, pos) => acc + (pos.shares || 0), 0)

  const fmtPnl = (val: number) => {
    const isPos = val >= 0
    return (
      <span style={{ color: isPos ? '#00C896' : '#FF4757', fontWeight: 900 }}>
        {isPos ? '+' : ''}${Math.abs(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    )
  }

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
              <DetailItem label="Cantidad" val={`${selectedPos.shares >= 0 ? '+' : ''}${selectedPos.shares}`} color={selectedPos.shares >= 0 ? '#FFF' : '#FF4757'} />
              <DetailItem label="Stop Loss (SL)" val={selectedPos.sl_price ? `$${selectedPos.sl_price}` : '—'} color="#FF4757" />
              <DetailItem label="Take Profit (TP)" val={selectedPos.tp_price ? `$${selectedPos.tp_price}` : '—'} color="#00C896" />
              <DetailItem label="Inversión" val={`$${selectedPos.total_cost?.toLocaleString()}`} color="#AAA" />
              <DetailItem label="Razón" val={selectedPos.exit_reason || 'ABIERTA'} color={selectedPos.status === 'open' ? '#00C896' : '#AAA'} />
              
              <div style={{ gridColumn: 'span 2', background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '16px', marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                   <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>P&L {(selectedPos.status === 'open' ? 'No Realizado' : 'Realizado')}</p>
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
          <h1 style={{ fontSize: '28px', fontWeight: 900, margin: 0, letterSpacing: '-0.03em' }}>💼 Positions Stocks</h1>
          <p style={{ color: '#666', fontSize: '14px', marginTop: '5px' }}>Gestión de posiciones industriales v5.0</p>
        </div>
      </div>

      {/* SUMMARY CARDS */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '25px', marginBottom: '40px' }}>
        <SummaryCard 
          title="Open Risk" 
          val={`${positions.length}/5`} 
          sub="Max open operations" 
          color="#FFF" 
        />
        <SummaryCard 
          title="Live P&L" 
          val={fmtPnl(totalPnL)} 
          sub="Unrealized aggregated" 
          color={totalPnL >= 0 ? '#00C896' : '#FF4757'} 
        />
        <SummaryCard 
          title="Total Portfolio Value" 
          val={`$${(totalCost + totalPnL).toLocaleString(undefined, { minimumFractionDigits: 2 })}`} 
          sub={`${totalShares} shares across ${positions.length} stocks`} 
          color="#4FC3F7" 
        />
      </div>

      {/* TABS */}
      <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <div style={{ display: 'flex', background: 'rgba(255,255,255,0.03)', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
          <TabButton active={tab === 'open'} onClick={() => setTab('open')} label={`Open Positions (${positions.length})`} />
          <TabButton active={tab === 'closed'} onClick={() => setTab('closed')} label="Closed History" />
        </div>

        <div style={{ overflowX: 'auto' }}>
          {tab === 'open' ? (
            <div style={{ minWidth: '1000px' }}>
              <div style={TableHeadStyle}>
                <span>Ticker</span>
                <span>Side</span>
                <span>Grupo</span>
                <span>Fecha</span>
                <span>Shares</span>
                <span>Avg</span>
                <span>Actual</span>
                <span style={{ textAlign: 'center' }}>DCA</span>
                <span style={{ textAlign: 'right' }}>PnL (%)</span>
                <span style={{ textAlign: 'right' }}>Acción</span>
              </div>

              {loading && <div style={LoadingStyle}>Cargando portafolio...</div>}
              {!loading && positions.length === 0 && <div style={LoadingStyle}>No hay posiciones abiertas.</div>}
              
              {!loading && positions.map((pos, i) => (
                <div key={`open-${pos.id || i}`} style={{ ...TableRowStyle, background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{ 
                        width: '3px', height: '24px', borderRadius: '4px',
                        background: pos.side?.toUpperCase() === 'SELL' ? '#ff4757' : '#00C896',
                        boxShadow: pos.side?.toUpperCase() === 'SELL' ? '0 0 10px #ff4757' : '0 0 10px #00C896'
                    }}></div>
                    <span style={{ fontWeight: 900, fontSize: '15px' }}>{pos.ticker}</span>
                  </div>
                  <span style={{ fontSize: '10px', fontWeight: 900, color: pos.side?.toUpperCase() === 'SELL' ? '#FF4757' : '#00C896' }}>{pos.side?.toUpperCase() || 'BUY'}</span>
                  <span><GroupBadge group={pos.group_name} /></span>
                  <span style={{ fontSize: '11px', color: '#666' }}>{pos.first_buy_at ? new Date(pos.first_buy_at).toLocaleDateString() : '—'}</span>
                  <span style={{ fontWeight: 700, color: pos.shares >= 0 ? '#FFF' : '#FF4757' }}>{pos.shares >= 0 ? '+' : ''}{pos.shares}</span>
                  <span style={{ color: '#AAA', fontSize: '13px' }}>${pos.avg_price?.toFixed(2)}</span>
                  <span style={{ fontWeight: 700, fontSize: '13px', color: '#4FC3F7' }}>${pos.current_price?.toFixed(2)}</span>
                  <span style={{ color: pos.dca_count > 0 ? '#CE93D8' : '#444', fontWeight: 800, textAlign: 'center' }}>{pos.dca_count > 0 ? `×${pos.dca_count}` : '—'}</span>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ margin: 0, fontWeight: 900, color: (pos.unrealized_pnl || 0) >= 0 ? '#00C896' : '#FF4757' }}>
                      {(pos.unrealized_pnl || 0) >= 0 ? '+' : ''}${(pos.unrealized_pnl || 0).toFixed(2)}
                    </p>
                    <p style={{ margin: 0, fontSize: '11px', color: (pos.unrealized_pnl_pct || 0) >= 0 ? '#00C896' : '#FF4757', opacity: 0.8 }}>
                      {(pos.unrealized_pnl_pct || 0) >= 0 ? '+' : ''}{(pos.unrealized_pnl_pct || 0).toFixed(2)}%
                    </p>
                  </div>
                  <div style={{ textAlign: 'right', display: 'flex', gap: '8px', justifyContent: 'flex-end', minWidth: '120px' }}>
                     <button 
                       onClick={() => setSelectedPos(pos)} 
                       style={{ ...DetailButtonStyle, background: 'rgba(0,123,255,0.05)', color: '#007BFF', border: '1px solid rgba(0,123,255,0.1)' }}
                       title="Ver Detalles"
                     >
                       ℹ️
                     </button>
                     <button 
                       onClick={async () => {
                         if (confirm(`¿Cerrar posición de ${pos.ticker} manualmente? Se enviará al historial.`)) {
                           try {
                             const res = await fetch(`/api/v1/positions/stocks/${pos.id}/close`, { method: 'POST' })
                             if (res.ok) {
                               fetchData()
                             } else {
                               alert("Error al cerrar posición")
                             }
                           } catch (err) {
                             console.error("Close error:", err)
                           }
                         }
                       }} 
                       style={{ ...DetailButtonStyle, background: 'rgba(0,200,150,0.05)', color: '#00C896', border: '1px solid rgba(0,200,150,0.1)' }}
                       title="Cerrar (Historial)"
                     >
                       ✓
                     </button>
                     <button 
                       onClick={async () => {
                         if (confirm(`¿ELIMINAR registro de ${pos.ticker} permanentemente?`)) {
                           try {
                             const res = await fetch(`/api/v1/positions/stocks/${pos.id}`, { method: 'DELETE' })
                             if (res.ok) {
                               fetchData()
                             } else {
                               alert("Error al eliminar registro")
                             }
                           } catch (err) {
                             console.error("Delete error:", err)
                           }
                         }
                       }} 
                       style={{ ...DetailButtonStyle, background: 'rgba(255,71,87,0.05)', color: '#FF4757', border: '1px solid rgba(255,71,87,0.1)' }}
                       title="ELIMINAR"
                     >
                       🗑️
                     </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ minWidth: '1000px' }}>
              <div style={TableHeadStyle}>
                <span>Ticker</span>
                <span>Grupo</span>
                <span>Entrada</span>
                <span>Salida</span>
                <span>Entry $</span>
                <span>Exit $</span>
                <span>Shares</span>
                <span style={{ textAlign: 'center' }}>Reason</span>
                <span style={{ textAlign: 'right' }}>PnL (%)</span>
                <span style={{ textAlign: 'right' }}>Acción</span>
              </div>

              {closedPositions.length === 0 && <div style={LoadingStyle}>No hay historial de posiciones cerradas.</div>}
              
              {closedPositions.map((pos, i) => (
                <div key={`closed-${pos.id || i}`} style={{ ...TableRowStyle, background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{ 
                        width: '3px', height: '24px', borderRadius: '4px', opacity: 0.5,
                        background: pos.side?.toUpperCase() === 'SELL' ? '#ff4757' : '#00C896',
                        boxShadow: pos.side?.toUpperCase() === 'SELL' ? '0 0 10px #ff4757' : '0 0 10px #00C896'
                    }}></div>
                    <span style={{ fontWeight: 900, fontSize: '15px' }}>{pos.ticker}</span>
                  </div>
                  <span><GroupBadge group={pos.group_name} /></span>
                  <span style={{ fontSize: '10px', color: '#555' }}>{pos.first_buy_at ? new Date(pos.first_buy_at).toLocaleDateString() : '—'}</span>
                  <span style={{ fontSize: '10px', color: '#666' }}>{pos.updated_at ? new Date(pos.updated_at).toLocaleDateString() : '—'}</span>
                  <span style={{ color: '#AAA', fontSize: '13px' }}>${pos.avg_price?.toFixed(2)}</span>
                  <span style={{ fontWeight: 700, fontSize: '13px' }}>${pos.current_price?.toFixed(2)}</span>
                  <span style={{ fontSize: '13px', color: pos.shares >= 0 ? '#AAA' : '#FF4757/70' }}>{pos.shares >= 0 ? '+' : ''}{pos.shares}</span>
                  <span style={{ textAlign: 'center' }}><ReasonBadge reason={pos.exit_reason || 'closed'} /></span>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ margin: 0, fontWeight: 900, color: (pos.unrealized_pnl || 0) >= 0 ? '#00C896' : '#FF4757' }}>
                      {(pos.unrealized_pnl || 0) >= 0 ? '+' : ''}${(pos.unrealized_pnl || 0).toFixed(2)}
                    </p>
                    <p style={{ margin: 0, fontSize: '11px', color: (pos.unrealized_pnl_pct || 0) >= 0 ? '#00C896' : '#FF4757', opacity: 0.8 }}>
                      {(pos.unrealized_pnl_pct || 0) >= 0 ? '+' : ''}{(pos.unrealized_pnl_pct || 0).toFixed(2)}%
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                     <button onClick={() => setSelectedPos(pos)} style={DetailButtonStyle}>Info</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div style={{ marginTop: '30px' }}>
        <Link href="/stocks/opportunities" style={{ color: '#00C896', textDecoration: 'none', fontWeight: 800, fontSize: '12px', letterSpacing: '0.05em' }}>
          ← IR AL SCANNER DE OPORTUNIDADES
        </Link>
      </div>
    </div>
  )
}

function SummaryCard({ title, val, sub, color }: any) {
  return (
    <div style={{ 
      background: 'rgba(255,255,255,0.03)', padding: '25px', borderRadius: '24px', 
      border: '1px solid rgba(255,255,255,0.05)', position: 'relative', overflow: 'hidden' 
    }}>
      <div style={{ position: 'absolute', top: 0, left: 0, width: '4px', height: '100%', background: color }}></div>
      <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em' }}>{title}</p>
      <div style={{ margin: '10px 0', fontSize: '28px', fontWeight: 900 }}>{val}</div>
      <p style={{ margin: 0, fontSize: '12px', color: '#444', fontWeight: 600 }}>{sub}</p>
    </div>
  )
}

function TabButton({ active, onClick, label }: any) {
  return (
    <button 
      onClick={onClick} 
      style={{ 
        flex: 1, padding: '20px', border: 'none', background: active ? 'rgba(255,255,255,0.02)' : 'transparent',
        color: active ? '#00C896' : '#555', fontWeight: 900, cursor: 'pointer', transition: '0.2s',
        borderBottom: active ? '2px solid #00C896' : '1px solid transparent', fontSize: '13px',
        textTransform: 'uppercase', letterSpacing: '0.05em'
      }}
    >
      {label}
    </button>
  )
}

function GroupBadge({ group }: { group: string }) {
  const isPro = group === 'inversiones_pro'
  return (
    <span style={{ 
      fontSize: '9px', fontWeight: 800, 
      color: isPro ? '#4FC3F7' : '#FF8A65',
      background: isPro ? 'rgba(79,195,247,0.1)' : 'rgba(255,138,101,0.1)',
      padding: '4px 8px', borderRadius: '4px', textTransform: 'uppercase'
    }}>
      {isPro ? 'PRO' : 'HOT'}
    </span>
  )
}

function ReasonBadge({ reason }: { reason: string }) {
  const isWin = !reason.toLowerCase().includes('sl') && !reason.toLowerCase().includes('stop')
  return (
    <span style={{ 
      fontSize: '8px', fontWeight: 900, 
      color: isWin ? '#00C896' : '#FF4757',
      border: `1px solid ${isWin ? 'rgba(0,200,150,0.2)' : 'rgba(255,71,87,0.2)'}`,
      padding: '3px 6px', borderRadius: '4px', textTransform: 'uppercase'
    }}>
      {reason.replace('_', ' ')}
    </span>
  )
}

function DetailItem({ label, val, color }: any) {
  return (
    <div>
      <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</p>
      <p style={{ margin: '4px 0 0 0', fontSize: '14px', fontWeight: 700, color: color || '#FFF' }}>{val || '—'}</p>
    </div>
  )
}

const TableHeadStyle = {
  display: 'grid', 
  gridTemplateColumns: '80px 60px 80px 105px 70px 85px 85px 50px 120px 100px', 
  padding: '16px 30px', 
  background: 'rgba(255,255,255,0.01)',
  fontSize: '10px', 
  fontWeight: 900, 
  color: '#444', 
  textTransform: 'uppercase' as const,
  letterSpacing: '0.1em',
  borderBottom: '1px solid rgba(255,255,255,0.03)'
}

const TableRowStyle = {
  display: 'grid', 
  gridTemplateColumns: '80px 60px 80px 105px 70px 85px 85px 50px 120px 100px', 
  padding: '18px 30px', 
  borderBottom: '1px solid rgba(255,255,255,0.02)',
  alignItems: 'center'
}

const LoadingStyle = { padding: '80px', textAlign: 'center' as const, color: '#333', fontSize: '13px', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.1em' }

const DetailButtonStyle = { 
  background: 'rgba(0,200,150,0.05)', border: '1px solid rgba(0,200,150,0.1)', 
  color: '#00C896', fontSize: '10px', fontWeight: 900, 
  padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', textTransform: 'uppercase' as const 
}

