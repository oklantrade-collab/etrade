"use client"
import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { formatDateInTimezone } from '@/lib/timezone'

export default function StocksPositions() {
  const [positions, setPositions] = useState<any[]>([])
  const [closedPositions, setClosedPositions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [hasMounted, setHasMounted] = useState(false)
  const [selectedPos, setSelectedPos] = useState<any>(null)
  const [tab, setTab] = useState<'open' | 'closed'>('open')
  const [showChart, setShowChart] = useState(false)
  const [selectedTicker, setSelectedTicker] = useState('')
  const [closedPage, setClosedPage] = useState(0)
  const [tz, setTz] = useState('America/Lima')
  const [selectedDiagPos, setSelectedDiagPos] = useState<any>(null)
  const [refreshingDiag, setRefreshingDiag] = useState(false)

  const handleRefreshDiag = async (posId: string) => {
    setRefreshingDiag(true)
    try {
      const res = await fetch(`/api/v1/stocks/positions/${posId}/diagnostics/refresh`, { method: 'POST' })
      if (res.ok) {
        const data = await res.json()
        if (data.diagnostics) {
          setSelectedDiagPos((prev: any) => prev ? { ...prev, diagnostics: data.diagnostics } : null)
          setPositions(prev => prev.map(p => p.id === posId ? { ...p, diagnostics: data.diagnostics } : p))
        }
      }
    } catch (e) {
      console.error("Error refreshing diagnostics:", e)
    } finally {
      setRefreshingDiag(false)
    }
  }

  useEffect(() => {
    const handleTzUpdate = () => {
      setTz(localStorage.getItem('app_timezone') || 'America/Lima')
    }
    window.addEventListener('timezoneUpdated', handleTzUpdate)
    handleTzUpdate()
    return () => window.removeEventListener('timezoneUpdated', handleTzUpdate)
  }, [])
  const ITEMS_PER_PAGE = 10

  useEffect(() => {
    setHasMounted(true)
    fetchData()
    const interval = setInterval(fetchData, 30000)
    return () => clearInterval(interval)
  }, [])

  const fetchData = async () => {
    try {
      const [openRes, closedRes] = await Promise.all([
        fetch('/api/v1/stocks/positions'),
        fetch('/api/v1/stocks/journal?limit=100')
      ])
      
      if (!openRes.ok || !closedRes.ok) throw new Error('API Error')

      const openData = await openRes.json()
      const rawOpen = Array.isArray(openData.positions) ? openData.positions : []
      const filteredOpen = rawOpen.filter((p: any) => 
        p.group_name !== 'OPTIONS' && 
        !String(p.ticker || '').includes(':OPT') &&
        !String(p.strategy || '').toUpperCase().startsWith('OPT')
      )
      setPositions(filteredOpen)

      const closedData = await closedRes.json()
      const rawClosed = Array.isArray(closedData) ? closedData : (Array.isArray(closedData?.positions) ? closedData.positions : [])
      const filteredClosed = rawClosed.filter((p: any) =>
        p.group_name !== 'OPTIONS' &&
        !String(p.ticker || '').includes(':OPT') &&
        !String(p.strategy || '').toUpperCase().startsWith('OPT')
      )
      setClosedPositions(filteredClosed)
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
        <div 
          onClick={() => setSelectedPos(null)}
          style={{ 
            position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', 
            background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(10px)', 
            zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer'
          }}
        >
          <div 
            onClick={e => e.stopPropagation()}
            style={{ 
              background: '#12161F', width: '500px', maxHeight: '90vh', borderRadius: '24px', 
              border: '1px solid rgba(255,255,255,0.1)', overflow: 'hidden',
              boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)',
              display: 'flex', flexDirection: 'column',
              cursor: 'default'
            }}
          >
            <div style={{ padding: '30px', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <h2 style={{ fontSize: '22px', fontWeight: 900, margin: 0 }}>{selectedPos.ticker}</h2>
                <p style={{ color: '#00C896', fontSize: '10px', fontWeight: 800, textTransform: 'uppercase', margin: '4px 0 0 0' }}>Detalle de Posición</p>
              </div>
              <button onClick={() => setSelectedPos(null)} style={{ background: 'rgba(255,255,255,0.05)', border: 'none', color: '#FFF', width: '32px', height: '32px', borderRadius: '50%', cursor: 'pointer', fontWeight: 900 }}>×</button>
            </div>
            
            <div style={{ padding: '30px', overflowY: 'auto', flex: 1, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <DetailItem label="Empresa" val={selectedPos.company_name} color="#FFF" />
              <DetailItem label="Sector" val={selectedPos.sector} color="#FFF" />
              <DetailItem label="Fecha Entrada" val={formatDateInTimezone(selectedPos.first_buy_at || selectedPos.entry_date, 'both')} color="#AAA" />
              <DetailItem label="Tipo Orden" val={selectedPos.order_type || 'MARKET'} color="#00C896" />
              <DetailItem label="Precio Entrada" val={`$${(selectedPos.avg_price || selectedPos.entry_price)?.toFixed(2)}`} color="#FFF" />
              <DetailItem label="Cantidad" val={`${selectedPos.shares >= 0 ? '+' : ''}${selectedPos.shares}`} color={selectedPos.shares >= 0 ? '#FFF' : '#FF4757'} />
              {(selectedPos.exit_date || selectedPos.closed_at) && (
                <>
                  <DetailItem label="Fecha Salida" val={formatDateInTimezone(selectedPos.exit_date || selectedPos.closed_at || selectedPos.updated_at, 'both')} color="#AAA" />
                  <DetailItem label="Precio Salida" val={`$${(selectedPos.exit_price || selectedPos.close_price || selectedPos.current_price)?.toFixed(2)}`} color="#FFF" />
                </>
              )}
              {(!selectedPos.exit_date && !selectedPos.closed_at) && (
                <>
                  <DetailItem label="Stop Loss (SL)" val={selectedPos.stop_loss ? `$${parseFloat(selectedPos.stop_loss).toFixed(2)}` : '—'} color="#FF4757" />
                  <DetailItem label="Take Profit (TP)" val={selectedPos.take_profit ? `$${parseFloat(selectedPos.take_profit).toFixed(2)}` : '—'} color="#00C896" />
                </>
              )}
              <DetailItem label="Inversión" val={`$${((selectedPos.total_cost) || (selectedPos.entry_price * Math.abs(selectedPos.shares)) || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`} color="#AAA" />
              
              <div style={{ gridColumn: 'span 2', background: 'rgba(255,255,255,0.02)', padding: '15px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '10px' }}>
                <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Estrategia de Compra</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '5px' }}>
                   <StrategyBadge strategy={selectedPos.strategy || selectedPos.rule_code} />
                   <p style={{ margin: 0, fontSize: '11px', color: '#AAA', lineHeight: '1.4' }}>
                     {STRATEGY_MAP[selectedPos.strategy?.toUpperCase()?.replace(' ', '_')]?.desc || STRATEGY_MAP[selectedPos.rule_code]?.desc || 'Estrategia de entrada algorítmica basada en parámetros de mercado.'}
                   </p>
                </div>
              </div>

              <div style={{ gridColumn: 'span 2', background: 'rgba(255,255,255,0.02)', padding: '15px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Estrategia de Cierre</p>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginTop: '5px' }}>
                   <ReasonBadge reason={selectedPos.exit_reason || selectedPos.close_reason || 'ABIERTA'} />
                   <p style={{ margin: 0, fontSize: '11px', color: '#AAA', lineHeight: '1.4' }}>
                     {REASON_MAP[selectedPos.exit_reason || selectedPos.close_reason]?.desc || 'Posición actualmente en mercado. Se aplican reglas de salida adaptativas.'}
                   </p>
                </div>
              </div>
              
              <div style={{ gridColumn: 'span 2', background: 'rgba(255,255,255,0.02)', padding: '20px', borderRadius: '16px', marginTop: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                   <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>P&L {(selectedPos.status === 'open' || !selectedPos.exit_date ? 'No Realizado' : 'Realizado')}</p>
                   <p style={{ margin: 0, fontSize: '24px', fontWeight: 900, color: (selectedPos.unrealized_pnl || selectedPos.pnl_usd || 0) >= 0 ? '#00C896' : '#FF4757' }}>
                     {(selectedPos.unrealized_pnl || selectedPos.pnl_usd || 0) >= 0 ? '+' : ''}${(selectedPos.unrealized_pnl || selectedPos.pnl_usd || 0).toFixed(2)}
                   </p>
                </div>
                <div style={{ textAlign: 'right' }}>
                   <p style={{ margin: 0, fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>Retorno (ROI)</p>
                   <p style={{ margin: 0, fontSize: '20px', fontWeight: 900, color: (selectedPos.unrealized_pnl_pct || selectedPos.pnl_pct || 0) >= 0 ? '#00C896' : '#FF4757' }}>
                     {(selectedPos.unrealized_pnl_pct || selectedPos.pnl_pct || 0) >= 0 ? '+' : ''}{(selectedPos.unrealized_pnl_pct || selectedPos.pnl_pct || 0).toFixed(2)}%
                   </p>
                </div>
              </div>

              {/* Nuevos bloques integrados del expander */}
              {selectedPos.status !== 'closed' && (
                <div style={{ gridColumn: 'span 2', display: 'flex', flexDirection: 'column', gap: '15px', marginTop: '10px' }}>
                  {selectedPos.tp_block1_price && <TPBlocksProgress position={selectedPos} />}
                  <SLAdaptiveBadge position={selectedPos} />
                </div>
              )}
            </div>
            
            <div style={{ padding: '20px 30px', background: 'rgba(255,255,255,0.02)', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
               <button onClick={() => setSelectedPos(null)} style={{ width: '100%', padding: '14px', borderRadius: '12px', border: 'none', background: '#00C896', color: '#000', fontWeight: 900, cursor: 'pointer', fontSize: '13px' }}>CERRAR DETALLES</button>
            </div>
          </div>
        </div>
      )}
      {showChart && <ChartModal symbol={selectedTicker} onClose={() => setShowChart(false)} />}
      {selectedDiagPos && (
        <PositionDiagnosticsModal 
          pos={selectedDiagPos} 
          onClose={() => setSelectedDiagPos(null)} 
          onRefresh={() => handleRefreshDiag(selectedDiagPos.id)}
          refreshing={refreshingDiag}
        />
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
              <div style={TableHeadOpenStyle}>
                <span>Ticker</span>
                <span style={{ textAlign: 'center' }}>Estado</span>
                <span>Side</span>
                <span>Grupo</span>
                <span>Fecha</span>
                <span>Shares</span>
                <span>Avg</span>
                <span>Actual</span>
                <span style={{ textAlign: 'center' }}>Estrategia Compra</span>
                <span style={{ textAlign: 'right' }}>PnL (%)</span>
                <span style={{ textAlign: 'right' }}>Chart</span>
                <span style={{ textAlign: 'right' }}>Acciones</span>
              </div>

              {loading && <div style={LoadingStyle}>Cargando portafolio...</div>}
              {!loading && positions.length === 0 && <div style={LoadingStyle}>No hay posiciones abiertas.</div>}
              
              {!loading && positions.map((pos, i) => (
                <div key={`open-${pos.id || i}`}>
                  <div style={{ ...TableRowOpenStyle, background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                      <div style={{ 
                          width: '4px', height: '24px', borderRadius: '4px',
                          background: pos.side?.toUpperCase() === 'SELL' ? '#ff4757' : '#00C896',
                          boxShadow: pos.side?.toUpperCase() === 'SELL' ? '0 0 12px rgba(255,71,87,0.4)' : '0 0 12px rgba(0,200,150,0.4)'
                      }}></div>
                      <span style={{ fontWeight: 900, fontSize: '16px', letterSpacing: '-0.02em' }}>{pos.ticker}</span>
                    </div>

                    {/* ESTADO / CHECK DE VALIDACIÓN CON TOOLTIP INTERACTIVO */}
                    <div style={{ display: 'flex', justifyContent: 'center' }}>
                      {pos.diagnostics?.is_valid ? (
                        <div 
                          onClick={() => setSelectedDiagPos(pos)}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: '4px',
                            background: 'rgba(0,200,150,0.12)', border: '1px solid rgba(0,200,150,0.35)',
                            borderRadius: '6px', padding: '3px 8px', cursor: 'pointer',
                            boxShadow: '0 0 10px rgba(0,200,150,0.15)', transition: 'transform 0.15s'
                          }}
                          title="✓ Todos los indicadores (BB, EMAs, Fib 1-6) y gestión de riesgo (SL, Trailing SL, TP) están completos y activos. Clic para ver radiografía completa."
                          onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.06)'}
                          onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
                        >
                          <span style={{ color: '#00C896', fontWeight: 900, fontSize: '10px', letterSpacing: '0.04em' }}>✓ OK</span>
                        </div>
                      ) : (
                        <div 
                          onClick={() => setSelectedDiagPos(pos)}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: '4px',
                            background: 'rgba(255,71,87,0.15)', border: '1px solid rgba(255,71,87,0.4)',
                            borderRadius: '6px', padding: '3px 8px', cursor: 'pointer',
                            boxShadow: '0 0 12px rgba(255,71,87,0.2)', transition: 'transform 0.15s'
                          }}
                          title={`❌ ATENCIÓN: Faltan variables o están en blanco:\n• ${pos.diagnostics?.missing_fields?.join('\n• ') || 'Sin diagnóstico'}\nClic para abrir radiografía.`}
                          onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.06)'}
                          onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
                        >
                          <span style={{ color: '#FF4757', fontWeight: 900, fontSize: '10px', letterSpacing: '0.04em' }}>❌ FALTAN</span>
                        </div>
                      )}
                    </div>

                    <span style={{ fontSize: '10px', fontWeight: 900, color: pos.side?.toUpperCase() === 'SELL' ? '#FF4757' : '#00C896' }}>{pos.side?.toUpperCase() || 'BUY'}</span>
                    <span><GroupBadge group={pos.group_name} /></span>
                    <div style={{ fontSize: '11px', color: '#666', lineHeight: '1.2' }}>
                      <div>{formatDateInTimezone(pos.first_buy_at, 'date')}</div>
                      <div style={{ fontSize: '9px', opacity: 0.6 }}>{formatDateInTimezone(pos.first_buy_at, 'time')}</div>
                    </div>
                    <span style={{ fontWeight: 700, color: pos.shares >= 0 ? '#FFF' : '#FF4757' }}>{pos.shares >= 0 ? '+' : ''}{pos.shares}</span>
                    <span style={{ color: '#AAA', fontSize: '13px' }}>${pos.avg_price?.toFixed(2)}</span>
                    <span style={{ fontWeight: 700, fontSize: '13px', color: '#4FC3F7' }}>${pos.current_price?.toFixed(2)}</span>
                    <span style={{ textAlign: 'center' }}><StrategyBadge strategy={pos.strategy} /></span>
                    <div style={{ textAlign: 'right' }}>
                      <p style={{ margin: 0, fontWeight: 900, color: (pos.unrealized_pnl || 0) >= 0 ? '#00C896' : '#FF4757' }}>
                        {(pos.unrealized_pnl || 0) >= 0 ? '+' : ''}${(pos.unrealized_pnl || 0).toFixed(2)}
                      </p>
                      <p style={{ margin: 0, fontSize: '11px', color: (pos.unrealized_pnl_pct || 0) >= 0 ? '#00C896' : '#FF4757', opacity: 0.8 }}>
                        {(pos.unrealized_pnl_pct || 0) >= 0 ? '+' : ''}{(pos.unrealized_pnl_pct || 0).toFixed(2)}%
                      </p>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                       <button 
                         onClick={() => { setSelectedTicker(pos.ticker); setShowChart(true); }}
                         style={{ ...DetailButtonStyle, background: 'rgba(56,189,248,0.1)', color: '#38BDF8', border: '1px solid rgba(56,189,248,0.2)', width: '26px', height: '26px', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                         title="Ver Gráfico"
                       >
                         📊
                       </button>
                    </div>
                    <div style={{ textAlign: 'right', display: 'flex', gap: '6px', justifyContent: 'flex-end', minWidth: '125px' }}>
                       <button 
                         onClick={() => setSelectedDiagPos(pos)} 
                         style={{ 
                           ...DetailButtonStyle, 
                           background: 'rgba(168,85,247,0.12)', 
                           color: '#C084FC', 
                           border: '1px solid rgba(168,85,247,0.3)', 
                           width: '26px', 
                           height: '26px', 
                           padding: 0, 
                           display: 'flex', 
                           alignItems: 'center', 
                           justifyContent: 'center',
                           fontSize: '12px',
                           boxShadow: '0 2px 8px rgba(168,85,247,0.2)'
                         }}
                         title="Auditoría y Diagnóstico Técnico Flotante"
                       >
                         🛡️
                       </button>
                       <button 
                         onClick={() => setSelectedPos(pos)} 
                         style={{ 
                           ...DetailButtonStyle, 
                           background: '#4FC3F7', 
                           color: '#000', 
                           border: 'none', 
                           width: '26px', 
                           height: '26px', 
                           padding: 0, 
                           display: 'flex', 
                           alignItems: 'center', 
                           justifyContent: 'center',
                           fontSize: '12px',
                           boxShadow: '0 4px 10px rgba(79,195,247,0.3)',
                           transition: 'transform 0.2s'
                         }}
                         title="Ver Detalles"
                         onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.1)'}
                         onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
                       >
                         ℹ️
                       </button>
                       <button 
                         onClick={async () => {
                           if (confirm(`¿Cerrar posición de ${pos.ticker} manualmente? Se enviará al historial.`)) {
                             try {
                               const res = await fetch(`/api/v1/stocks/positions/${pos.id}/close`, { method: 'POST' })
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
                               const res = await fetch(`/api/v1/stocks/positions/${pos.id}`, { method: 'DELETE' })
                               if (res.ok) {
                                setPositions(prev => prev.filter((p: any) => p.id !== pos.id))
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
                  {/* Información ahora integrada en el modal de detalles */}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ minWidth: '1000px' }}>
              <div style={TableHeadClosedStyle}>
                <span>Ticker</span>
                <span>Grupo</span>
                <span style={{ textAlign: 'center' }}>Estrategia Compra</span>
                <span>Entrada</span>
                <span>Salida</span>
                <span>Entry $</span>
                <span>Exit $</span>
                <span>Shares</span>
                <span style={{ textAlign: 'center' }}>Estrategia Cierre</span>
                <span style={{ textAlign: 'right' }}>PnL (%)</span>
                <span style={{ textAlign: 'right' }}>Chart</span>
                <span style={{ textAlign: 'right' }}>Det.</span>
              </div>

              {closedPositions.length === 0 && <div style={LoadingStyle}>No hay historial de posiciones cerradas.</div>}
              
              {closedPositions.slice(closedPage * ITEMS_PER_PAGE, (closedPage + 1) * ITEMS_PER_PAGE).map((pos, i) => (
                <div key={`closed-${pos.id || i}`} style={{ ...TableRowClosedStyle, background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{ 
                        width: '3px', height: '24px', borderRadius: '4px', opacity: 0.5,
                        background: pos.side?.toUpperCase() === 'SELL' ? '#ff4757' : '#00C896',
                        boxShadow: pos.side?.toUpperCase() === 'SELL' ? '0 0 10px #ff4757' : '0 0 10px #00C896'
                    }}></div>
                    <span style={{ fontWeight: 900, fontSize: '15px' }}>{pos.ticker}</span>
                  </div>
                  <span><GroupBadge group={pos.group_name} /></span>
                  <span style={{ textAlign: 'center' }}><StrategyBadge strategy={pos.strategy || pos.rule_code} /></span>
                  <div style={{ fontSize: '10px', color: '#555', lineHeight: '1.2' }}>
                    <div>{formatDateInTimezone(pos.first_buy_at || pos.entry_date, 'date')}</div>
                    <div style={{ fontSize: '8px', opacity: 0.5 }}>{formatDateInTimezone(pos.first_buy_at || pos.entry_date, 'time')}</div>
                  </div>
                  <div style={{ fontSize: '10px', color: '#666', lineHeight: '1.2' }}>
                    <div>{formatDateInTimezone(pos.updated_at || pos.exit_date, 'date')}</div>
                    <div style={{ fontSize: '8px', opacity: 0.5 }}>{formatDateInTimezone(pos.updated_at || pos.exit_date, 'time')}</div>
                  </div>
                  <span style={{ color: '#AAA', fontSize: '13px' }}>${(pos.avg_price || pos.entry_price)?.toFixed(2)}</span>
                  <span style={{ fontWeight: 700, fontSize: '13px' }}>${(pos.current_price || pos.exit_price)?.toFixed(2)}</span>
                  <span style={{ fontSize: '13px', color: pos.shares >= 0 ? '#AAA' : '#FF4757/70' }}>{pos.shares >= 0 ? '+' : ''}{pos.shares}</span>
                  <span style={{ textAlign: 'center' }}><ReasonBadge reason={pos.exit_reason || 'closed'} /></span>
                  <div style={{ textAlign: 'right' }}>
                    <p style={{ margin: 0, fontWeight: 900, color: (pos.pnl_usd || pos.unrealized_pnl || 0) >= 0 ? '#00C896' : '#FF4757' }}>
                      {(pos.pnl_usd || pos.unrealized_pnl || 0) >= 0 ? '+' : ''}${(pos.pnl_usd || pos.unrealized_pnl || 0).toFixed(2)}
                    </p>
                    <p style={{ margin: 0, fontSize: '11px', color: (pos.pnl_pct || pos.unrealized_pnl_pct || 0) >= 0 ? '#00C896' : '#FF4757', opacity: 0.8 }}>
                      {(pos.pnl_pct || pos.unrealized_pnl_pct || 0) >= 0 ? '+' : ''}{(pos.pnl_pct || pos.unrealized_pnl_pct || 0).toFixed(2)}%
                    </p>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                      <button 
                         onClick={() => { setSelectedTicker(pos.ticker); setShowChart(true); }}
                         style={{ ...DetailButtonStyle, background: 'rgba(56,189,248,0.1)', color: '#38BDF8', border: '1px solid rgba(56,189,248,0.2)', width: '26px', height: '26px', padding: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
                         title="Ver Gráfico"
                       >
                         📊
                       </button>
                  </div>
                  <div style={{ textAlign: 'right', display: 'flex', gap: '8px', justifyContent: 'flex-end', minWidth: '80px' }}>
                     <button 
                       onClick={() => setSelectedPos(pos)} 
                       style={{ 
                         ...DetailButtonStyle, 
                         background: '#4FC3F7', 
                         color: '#000', 
                         border: 'none', 
                         width: '26px', 
                         height: '26px', 
                         padding: 0, 
                         display: 'flex', 
                         alignItems: 'center', 
                         justifyContent: 'center',
                         fontSize: '12px',
                         boxShadow: '0 4px 10px rgba(79,195,247,0.3)',
                         transition: 'transform 0.2s'
                       }}
                       title="Ver Detalles"
                       onMouseOver={(e) => e.currentTarget.style.transform = 'scale(1.1)'}
                       onMouseOut={(e) => e.currentTarget.style.transform = 'scale(1)'}
                     >
                       ℹ️
                     </button>
                     <button 
                       onClick={async () => {
                         if (confirm(`¿ELIMINAR registro de ${pos.ticker} permanentemente?`)) {
                           try {
                             const res = await fetch(`/api/v1/stocks/positions/${pos.id}`, { method: 'DELETE' })
                             if (res.ok) {
                                setClosedPositions(prev => prev.filter((p: any) => p.id !== pos.id))
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

              {/* PAGINATION CONTROLS */}
              {closedPositions.length > ITEMS_PER_PAGE && (
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '16px', padding: '24px 0', borderTop: '1px solid rgba(255,255,255,0.05)', background: 'rgba(255,255,255,0.01)' }}>
                  <button 
                    onClick={() => setClosedPage(p => Math.max(0, p - 1))}
                    disabled={closedPage === 0}
                    style={{ padding: '8px 16px', borderRadius: '8px', background: '#12161F', border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', cursor: 'pointer', fontSize: '0.8rem', opacity: closedPage === 0 ? 0.3 : 1 }}
                  >
                    Anterior
                  </button>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    {[...Array(Math.ceil(closedPositions.length / ITEMS_PER_PAGE))].map((_, i) => (
                      <button 
                        key={i}
                        onClick={() => setClosedPage(i)}
                        style={{ 
                          width: '32px', 
                          height: '32px', 
                          borderRadius: '6px', 
                          cursor: 'pointer', 
                          fontWeight: 'bold', 
                          fontSize: '0.8rem', 
                          background: closedPage === i ? '#00C896' : '#12161F', 
                          color: closedPage === i ? '#000' : '#888',
                          border: closedPage === i ? 'none' : '1px solid rgba(255,255,255,0.1)'
                        }}
                      >
                        {i + 1}
                      </button>
                    ))}
                  </div>
                  <button 
                    onClick={() => setClosedPage(p => Math.min(Math.ceil(closedPositions.length / ITEMS_PER_PAGE) - 1, p + 1))}
                    disabled={closedPage >= Math.ceil(closedPositions.length / ITEMS_PER_PAGE) - 1}
                    style={{ padding: '8px 16px', borderRadius: '8px', background: '#12161F', border: '1px solid rgba(255,255,255,0.1)', color: '#FFF', cursor: 'pointer', fontSize: '0.8rem', opacity: closedPage >= Math.ceil(closedPositions.length / ITEMS_PER_PAGE) - 1 ? 0.3 : 1 }}
                  >
                    Siguiente
                  </button>
                </div>
              )}
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

// --- CHART COMPONENTS ---

function TradingViewWidget({ symbol }: { symbol: string }) {
  const containerId = `tv-chart-${symbol}`;
  const containerRef = useRef<any>(null);
  const scriptLoaded = useRef(false);
  
  useEffect(() => {
    if (scriptLoaded.current) return;
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => {
      if ((window as any).TradingView && containerRef.current) {
        const tvTimezone = typeof window !== "undefined" ? (localStorage.getItem("app_timezone") || "America/Lima") : "America/Lima";

        new (window as any).TradingView.widget({
          "autosize": true,
          "symbol": symbol,
          "interval": "15",
          "timezone": tvTimezone,
          "theme": "dark",
          "style": "1",
          "locale": "es",
          "toolbar_bg": "#161922",
          "enable_publishing": false,
          "allow_symbol_change": true,
          "container_id": containerId,
          "backgroundColor": "#0F1117",
          "gridColor": "rgba(255, 255, 255, 0.05)",
          "hide_side_toolbar": false,
          "studies": [
            "BB@tv-basicstudies",
            "MAExp@tv-basicstudies",
            "MASimple@tv-basicstudies"
          ],
          "studies_overrides": {
            "moving average.length": 3,
            "moving average.plot.color": "#E3FF00",
            "moving average.ma.color": "#E3FF00",
            "moving average.linewidth": 2
          },
          "overrides": {
            "mainSeriesProperties.style": 1,
          }
        });
      }
    };
    document.head.appendChild(script);
    scriptLoaded.current = true;
  }, [symbol, containerId]);

  return (
    <div ref={containerRef} id={containerId} style={{ height: '100%', width: '100%', borderRadius: '16px', overflow: 'hidden', border: '1px solid rgba(255,255,255,0.1)' }} />
  );
}

function ChartModal({ symbol, onClose }: { symbol: string, onClose: () => void }) {
  return (
    <div style={{ position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1100, backdropFilter: 'blur(5px)' }}>
        <div style={{ background: '#0F1117', width: '95%', height: '92%', borderRadius: '24px', border: '1px solid #38BDF8', overflow: 'hidden', display: 'flex', flexDirection: 'column', boxShadow: '0 0 50px rgba(56,189,248,0.2)' }}>
            <div style={{ padding: '15px 25px', background: '#161922', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <h3 style={{ margin: 0, color: '#FFF', fontSize: '16px', fontWeight: 900 }}>GRÁFICO TÉCNICO: {symbol}</h3>
                <button onClick={onClose} style={{ background: '#EF4444', border: 'none', color: '#FFF', padding: '6px 15px', borderRadius: '8px', fontSize: '10px', fontWeight: 900, cursor: 'pointer' }}>CERRAR GRÁFICO</button>
            </div>
            <div style={{ flex: 1, background: '#000' }}>
                <TradingViewWidget symbol={symbol} />
            </div>
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

function StrategyBadge({ strategy }: { strategy: string }) {
  if (!strategy) return <span style={{ color: '#444' }}>—</span>
  const code = strategy?.toUpperCase()?.replace(' ', '_')
  const map = STRATEGY_MAP[code] || STRATEGY_MAP[strategy]
  
  return (
    <span style={{ 
      fontSize: '8px', fontWeight: 950, 
      color: '#CE93D8',
      background: 'rgba(206,147,216,0.1)',
      padding: '4px 6px', borderRadius: '4px', border: '1px solid rgba(206,147,216,0.2)',
      textTransform: 'uppercase'
    }}>
      {map ? map.label : strategy.replace('_', ' ')}
    </span>
  )
}

function GroupBadge({ group }: { group: string }) {
  const gUpper = String(group || '').toUpperCase()
  const isAlpha = gUpper.includes('ALPHA_RUNNER') || gUpper.includes('ALPHA')
  const isPro = group === 'inversiones_pro' || gUpper.includes('GIANT') || gUpper.includes('LEADER')
  return (
    <span style={{ 
      fontSize: '9px', fontWeight: 800, 
      color: isAlpha ? '#F59E0B' : (isPro ? '#4FC3F7' : '#FF8A65'),
      background: isAlpha ? 'rgba(245,158,11,0.14)' : (isPro ? 'rgba(79,195,247,0.1)' : 'rgba(255,138,101,0.1)'),
      border: isAlpha ? '1px solid rgba(245,158,11,0.35)' : 'none',
      padding: '4px 8px', borderRadius: '4px', textTransform: 'uppercase'
    }}>
      {isAlpha ? '⚡ ALPHA' : (isPro ? 'PRO' : 'HOT')}
    </span>
  )
}

const REASON_MAP: Record<string, { label: string, desc: string }> = {
  'AaEXT': { label: 'EXTENSIÓN ALTA', desc: 'Cierre preventivo por extensión excesiva del precio (RSI/Fibonacci).' },
  'V2_TOTAL_EMA_DOWN_OR_NEUTRAL': { label: 'TENDENCIA BAJISTA', desc: 'Las EMAs se han cruzado a la baja o están en modo neutral.' },
  'V2_TOTAL_EMA_UP_MID_SAR_NEG': { label: 'SAR NEGATIVO', desc: 'Reversión del SAR Parabolic mientras la tendencia EMA era alcista.' },
  'TP_V2_TOTAL_SIP_V_4H_SELL': { label: 'SIPV SELL (4H)', desc: 'Patrón de velas bajista detectado en temporalidad de 4 horas.' },
  'tp_v2_total_ALPHA_EXIT_2A_15M_WICK15_OPEN_RED': { label: 'CIERRE 2a (15M MECHA+ROJO)', desc: 'Vela 15m > BB Superior con mecha >=15% y toque de OPEN en rojo.' },
  'tp_v2_total_ALPHA_EXIT_2B_5M_WICK15_OPEN_RED': { label: 'CIERRE 2b (5M MECHA+ROJO)', desc: 'Vela 5m Open > BB Superior con mecha >=15% y toque de OPEN en rojo.' },
  'tp_v2_total_ALPHA_EXIT_2D3_5M_OPEN_ABOVE_BB_FIRST_RED': { label: 'CIERRE 2d-3 (5M 1ER ROJO)', desc: 'Vela 5m abrió sobre BB Superior y giró a rojo tocando OPEN.' },
  'ALPHA_EXIT_1B_UPPER6_1H_TP50': { label: 'PARCIAL 1b (UPPER_6 1H)', desc: 'Cierre parcial del 50% al tocar UPPER_6 en temporalidad de 1 Hora.' },
  'trailing_profit_lock': { label: 'TRAILING STOP B.5', desc: 'Ganancia asegurada por el Trailing Stop escalonado de 3 etapas.' },
  'eod_hard_exit_1550': { label: 'CIERRE EOD 15:50 ET', desc: 'Liquidación obligatoria de fin de día para cero riesgo overnight.' },
  'tp_band': { label: 'TAKE PROFIT BANDA', desc: 'El precio ha alcanzado la banda superior de Fibonacci (U6/L6).' },
  'sl': { label: 'STOP LOSS', desc: 'El precio ha tocado el límite de pérdida configurado.' },
  'tp': { label: 'TAKE PROFIT', desc: 'El precio ha alcanzado el objetivo de ganancia estándar.' },
  'proactive_exit': { label: 'SALIDA PROACTIVA', desc: 'Cierre anticipado por pérdida de momentum antes de tocar SL/TP.' },
  'recovery_exit': { label: 'SALIDA RECUPERACIÓN', desc: 'Cierre en modo recuperación tras un rebote técnico favorable.' },
}

const STRATEGY_MAP: Record<string, { label: string, desc: string }> = {
  'V5_INDUSTRIAL': { label: 'V5 INDUSTRIAL', desc: 'Estrategia institucional basada en acumulación de volumen y quiebre de estructura técnica.' },
  'HOT_CANDLE_BUY': { label: 'HOT CANDLE', desc: 'Entrada por momentum tras vela de alta convicción en zonas de soporte dinámico.' },
  'EMA_REVERSAL': { label: 'EMA REVERSAL', desc: 'Detección de cambio de tendencia mediante cruce optimizado de medias móviles.' },
  'BOLLINGER_EXT': { label: 'BOLLINGER EXT', desc: 'Explotación de extremos en bandas de Bollinger con confirmación de RSI.' },
  'PULLBACK_3A_EMA3_1H_DIP': { label: 'REGLA 3a (EMA3 1H)', desc: 'Compra en retroceso 1H Open<=EMA3 con extremo 5m/15m en BB_Lower o LOWER_5/6.' },
  'PULLBACK_4A_EMA1H_PINE_BUY': { label: 'REGLA 4a (PINE BUY)', desc: 'Rebote en EMA9/20 de 1H con señal PineScript BUY (< UPPER_3).' },
  'PULLBACK_4B_EMA1H_CROSS_3_9': { label: 'REGLA 4b (CRUCE 3/9)', desc: 'Rebote en EMA9/20 de 1H con cruce fresco EMA3 > EMA9 en 5m/15m.' },
  'PULLBACK_4C_EMA1H_BB5M_LOWER': { label: 'REGLA 4c (BB_LOW-Δ)', desc: 'Rebote en EMA9/20 de 1H tocando (BB_Inferior_5m - Delta).' },
  'PULLBACK_4D_EMA1H_SIPV_FIB': { label: 'REGLA 4d (SIPV FIB)', desc: 'Rebote en EMA9/20 de 1H con vela SIPV de cambio de tendencia en Basis..Upper_3.' },
  'PULLBACK_LOWER_ABSORPTION': { label: 'ABSORCIÓN LOWER 5/6', desc: 'Rebote con absorción de mecha inferior en banda extrema LOWER_5/6.' },
}

function ReasonBadge({ reason }: { reason: string }) {
  const code = reason?.split(' ')[0] || reason
  const map = REASON_MAP[code] || REASON_MAP[reason]
  const isWin = !reason.toLowerCase().includes('sl') && !reason.toLowerCase().includes('stop')
  
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
      <span style={{ 
        fontSize: '8px', fontWeight: 900, 
        color: isWin ? '#00C896' : '#FF4757',
        border: `1px solid ${isWin ? 'rgba(0,200,150,0.2)' : 'rgba(255,71,87,0.2)'}`,
        padding: '3px 6px', borderRadius: '4px', textTransform: 'uppercase'
      }}>
        {map ? map.label : reason.replace('_', ' ')}
      </span>
      {map && <span style={{ fontSize: '7px', color: '#555', fontWeight: 600 }}>{code}</span>}
    </div>
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

function TPBlocksProgress({ position }: { position: any }) {
  const b1 = position.tp_block1_executed
  const b2 = position.tp_block2_executed
  const b3 = position.tp_block3_executed
  const b1p = position.tp_block1_price
  const b2p = position.tp_block2_price
  const b3sl = position.tp_trailing_sl
  const strength = position.tp_buy_strength
  const price = position.current_price || 0

  const strengthConfig: Record<string, { color: string; label: string }> = {
    strong:   { color: '#00C896', label: 'FUERTE' },
    moderate: { color: '#FFB74D', label: 'MODERADA' },
    weak:     { color: '#FF4757', label: 'DÉBIL' },
  }
  const sc = strengthConfig[strength] || strengthConfig.moderate

  const blocks = [
    { n: 1, label: '50%', price: b1p, executed: b1, pnl: position.tp_block1_pnl, color: '#4FC3F7' },
    { n: 2, label: '25%', price: b2p, executed: b2, pnl: position.tp_block2_pnl, color: '#CE93D8' },
    { n: 3, label: '25%', price: b3sl ? `Trail $${parseFloat(b3sl).toFixed(2)}` : 'Trailing', executed: b3, pnl: position.tp_block3_pnl, color: '#FFB74D' },
  ]

  return (
    <div style={{
      background: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.06)',
      borderRadius: '10px',
      padding: '14px',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <span style={{ color: '#FFF', fontWeight: 700, fontSize: '13px' }}>📊 TP en 3 Bloques</span>
        <span style={{
          color: sc.color, fontSize: '10px',
          background: `${sc.color}22`,
          padding: '2px 8px', borderRadius: '4px', fontWeight: 700,
        }}>
          Fuerza: {sc.label}
        </span>
      </div>

      {/* Bloques */}
      {blocks.map(block => (
        <div key={block.n} style={{
          display: 'flex', alignItems: 'center', gap: '10px',
          padding: '8px 0',
          borderBottom: '1px solid rgba(255,255,255,0.04)',
          opacity: block.executed ? 0.6 : 1,
        }}>
          {/* Indicador circular */}
          <div style={{
            width: '28px', height: '28px', borderRadius: '50%',
            background: block.executed ? `${block.color}33` : 'rgba(255,255,255,0.05)',
            border: `2px solid ${block.executed ? block.color : (typeof block.price === 'number' && price >= block.price) ? block.color : 'rgba(255,255,255,0.15)'}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '12px', flexShrink: 0, color: block.executed ? block.color : '#888',
          }}>
            {block.executed ? '✓' : block.n}
          </div>

          {/* Info */}
          <div style={{ flex: 1 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
              <span style={{ color: '#CCC', fontSize: '12px', fontWeight: 600 }}>
                Bloque {block.n} ({block.label})
              </span>
              {block.executed && block.pnl > 0 && (
                <span style={{ color: '#00C896', fontSize: '11px', fontWeight: 700 }}>
                  +${parseFloat(block.pnl).toFixed(2)}
                </span>
              )}
            </div>
            <div style={{ color: '#555', fontSize: '11px', fontFamily: 'monospace' }}>
              {block.executed
                ? '✅ Ejecutado'
                : typeof block.price === 'number'
                ? `Trigger: $${parseFloat(block.price).toFixed(2)}`
                : `Trigger: ${block.price}`
              }
            </div>
          </div>
        </div>
      ))}

      {/* Trailing B3 info */}
      {b1 && b2 && !b3 && b3sl && (
        <div style={{
          marginTop: '8px', padding: '6px 10px',
          background: 'rgba(255,183,77,0.08)',
          borderRadius: '6px', fontSize: '11px', color: '#FFB74D'
        }}>
          🎯 Trailing activo: SL en ${parseFloat(b3sl).toFixed(2)}
        </div>
      )}
    </div>
  )
}

const TableHeadOpenStyle = {
  display: 'grid', 
  gridTemplateColumns: '80px 85px 45px 70px 90px 65px 75px 75px 90px 105px 35px 125px', 
  padding: '16px 25px', 
  background: 'rgba(255,255,255,0.01)',
  fontSize: '10px', 
  fontWeight: 900, 
  color: '#444', 
  textTransform: 'uppercase' as const,
  letterSpacing: '0.1em',
  borderBottom: '1px solid rgba(255,255,255,0.03)'
}

const TableRowOpenStyle = {
  display: 'grid', 
  gridTemplateColumns: '80px 85px 45px 70px 90px 65px 75px 75px 90px 105px 35px 125px', 
  padding: '18px 25px', 
  borderBottom: '1px solid rgba(255,255,255,0.02)',
  alignItems: 'center'
}

const TableHeadClosedStyle = {
  display: 'grid', 
  gridTemplateColumns: '70px 50px 80px 80px 80px 70px 70px 60px 150px 80px 40px 60px', 
  padding: '16px 20px', 
  background: 'rgba(255,255,255,0.01)',
  fontSize: '10px', 
  fontWeight: 900, 
  color: '#444', 
  textTransform: 'uppercase' as const,
  letterSpacing: '0.1em',
  borderBottom: '1px solid rgba(255,255,255,0.03)'
}

const TableRowClosedStyle = {
  display: 'grid', 
  gridTemplateColumns: '70px 50px 80px 80px 80px 70px 70px 60px 150px 80px 40px 60px', 
  padding: '18px 20px', 
  borderBottom: '1px solid rgba(255,255,255,0.02)',
  alignItems: 'center'
}

const LoadingStyle = { padding: '80px', textAlign: 'center' as const, color: '#333', fontSize: '13px', fontWeight: 700, textTransform: 'uppercase' as const, letterSpacing: '0.1em' }

const DetailButtonStyle = { 
  background: 'rgba(0,200,150,0.05)', border: '1px solid rgba(0,200,150,0.1)', 
  color: '#00C896', fontSize: '10px', fontWeight: 900, 
  padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', textTransform: 'uppercase' as const 
}

function SLAdaptiveBadge({ position }: { position: any }) {
  const mode     = position.sl_mode || 'monitoring'
  const lossPct  = parseFloat(position.sl_loss_pct || 0)
  const bounce   = parseFloat(position.sl_bounce_score || 0)
  const lowest   = parseFloat(position.sl_lowest_loss_pct || 0)
  const recovery = parseFloat(position.sl_recovery_from_low || 0)
  const days     = position.sl_waiting_days || 0

  const modeConfig: Record<string, any> = {
    monitoring: {
      label: '✅ Monitoreo',
      color: '#00C896',
      bg:    'rgba(0,200,150,0.08)',
    },
    warning: {
      label: '⚠️ Advertencia',
      color: '#FFB74D',
      bg:    'rgba(255,183,77,0.08)',
    },
    waiting: {
      label: '⏳ Esperando rebote',
      color: '#4FC3F7',
      bg:    'rgba(79,195,247,0.08)',
    },
    closing: {
      label: '🔴 Cerrando',
      color: '#FF4757',
      bg:    'rgba(255,71,87,0.08)',
    },
  }

  const cfg = modeConfig[mode] || modeConfig.monitoring

  // Solo mostramos el badge completo si hay algo de pérdida (<= -0.1) o si ya entró a un modo diferente a monitoring
  if (lossPct > -0.1 && mode === 'monitoring') {
      return (
          <div style={{
            background: 'rgba(255,255,255,0.02)',
            border: '1px solid rgba(255,255,255,0.06)',
            borderRadius: '10px',
            padding: '14px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#555', fontSize: '12px', fontStyle: 'italic'
          }}>
            Stop Loss en zona segura (Ganancia)
          </div>
      )
  }

  return (
    <div style={{
      background:   cfg.bg,
      border:       `1px solid ${cfg.color}33`,
      borderRadius: '10px',
      padding:      '14px',
      display:      'flex',
      flexDirection: 'column',
      justifyContent: 'center'
    }}>

      {/* Header */}
      <div style={{
        display:        'flex',
        justifyContent: 'space-between',
        alignItems:     'center',
        marginBottom:   '12px',
      }}>
        <span style={{
          color:      cfg.color,
          fontWeight: 700,
          fontSize:   '13px',
        }}>
          🛡️ SL: {cfg.label}
        </span>
        <span style={{
          color:      lossPct > -2 ? '#FFB74D'
                    : lossPct > -5 ? '#FF8A65'
                    : '#FF4757',
          fontWeight: 700,
          fontSize:   '14px',
          fontFamily: 'monospace',
        }}>
          {lossPct.toFixed(2)}%
        </span>
      </div>

      {/* Info row */}
      <div style={{
        display:  'grid',
        gridTemplateColumns: '1fr 1fr',
        gap:      '8px',
        fontSize: '11px',
      }}>
        <div>
          <span style={{color:'#777'}}>Mínimo: </span>
          <span style={{color:'#FF8A65', fontWeight:700}}>{lowest.toFixed(2)}%</span>
        </div>
        <div>
          <span style={{color:'#777'}}>Recuperó: </span>
          <span style={{color:'#00C896', fontWeight:700}}>+{recovery.toFixed(2)}%</span>
        </div>
        {mode === 'waiting' && (
          <>
            <div>
              <span style={{color:'#777'}}>Días espera: </span>
              <span style={{color:'#4FC3F7', fontWeight:700}}>{days}</span>
            </div>
            <div>
              <span style={{color:'#777'}}>Score rebote: </span>
              <span style={{
                fontWeight: 700,
                color: bounce >= 6
                  ? '#00C896'
                  : bounce >= 3
                  ? '#FFB74D'
                  : '#FF4757',
              }}>
                {bounce.toFixed(1)}/10
              </span>
            </div>
          </>
        )}
      </div>

      {/* Barra de rebote si está esperando */}
      {(mode === 'waiting' || mode === 'warning') && (
        <div style={{ marginTop:'12px' }}>
          <div style={{
            display:        'flex',
            justifyContent: 'space-between',
            fontSize:       '10px',
            color:          '#777',
            marginBottom:   '4px',
          }}>
            <span>Fuerza de Rebote (SIPV)</span>
            <span>{bounce.toFixed(1)}/10</span>
          </div>
          <div style={{
            height:       '6px',
            background:   'rgba(255,255,255,0.06)',
            borderRadius: '3px',
          }}>
            <div style={{
              width:        `${Math.min(100, Math.max(0, bounce * 10))}%`,
              height:       '100%',
              background:   bounce >= 7
                ? '#00C896'
                : bounce >= 4
                ? '#FFB74D'
                : '#FF4757',
              borderRadius: '3px',
              transition:   'width 0.5s',
              boxShadow:    `0 0 8px ${bounce >= 7 ? '#00C896' : bounce >= 4 ? '#FFB74D' : '#FF4757'}88`
            }} />
          </div>
        </div>
      )}
    </div>
  )
}

function PositionDiagnosticsModal({ pos, onClose, onRefresh, refreshing }: { pos: any, onClose: () => void, onRefresh: () => void, refreshing: boolean }) {
  const diag = pos?.diagnostics || {}
  const risk = diag.risk || {}
  const bollinger = diag.bollinger || {}
  const emas = diag.emas || {}
  const fib = diag.fibonacci || {}
  const isValid = !!diag.is_valid
  const missing = diag.missing_fields || []
  const curPrice = diag.current_price || pos.current_price || pos.avg_price || 0

  return (
    <div 
      onClick={onClose}
      style={{ 
        position: 'fixed', top: 0, left: 0, width: '100%', height: '100%', 
        background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(12px)', 
        zIndex: 1200, display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: '20px'
      }}
    >
      <div 
        onClick={e => e.stopPropagation()}
        style={{ 
          background: '#0D111A', width: '760px', maxHeight: '92vh', borderRadius: '24px', 
          border: '1px solid rgba(255,255,255,0.08)', overflow: 'hidden',
          boxShadow: '0 30px 60px rgba(0,0,0,0.8), 0 0 40px rgba(0,200,150,0.05)',
          display: 'flex', flexDirection: 'column'
        }}
      >
        {/* HEADER */}
        <div style={{ padding: '24px 30px', background: 'rgba(255,255,255,0.02)', borderBottom: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <h2 style={{ fontSize: '24px', fontWeight: 900, margin: 0, color: '#FFF' }}>{pos.ticker}</h2>
              <span style={{ 
                fontSize: '11px', fontWeight: 900, 
                padding: '4px 10px', borderRadius: '6px',
                background: isValid ? 'rgba(0,200,150,0.15)' : 'rgba(255,71,87,0.15)',
                color: isValid ? '#00C896' : '#FF4757',
                border: `1px solid ${isValid ? 'rgba(0,200,150,0.3)' : 'rgba(255,71,87,0.3)'}`
              }}>
                {isValid ? '✓ 100% VÁLIDO — OPERACIÓN PROTEGIDA' : `❌ INCOMPLETO (${missing.length} VARIABLES FALTANTES)`}
              </span>
            </div>
            <p style={{ margin: '4px 0 0 0', fontSize: '12px', color: '#888' }}>
              Precio actual: <span style={{ color: '#4FC3F7', fontWeight: 700 }}>${curPrice?.toFixed(2)}</span> | Entrada: ${pos.avg_price?.toFixed(2)} | Cantidad: {pos.shares} acciones
            </p>
          </div>
          <button 
            onClick={onClose} 
            style={{ background: 'rgba(255,255,255,0.05)', border: 'none', color: '#FFF', width: '34px', height: '34px', borderRadius: '50%', cursor: 'pointer', fontWeight: 900, fontSize: '18px' }}
          >
            ×
          </button>
        </div>

        {/* CONTENIDO SCROLLABLE */}
        <div style={{ padding: '24px 30px', overflowY: 'auto', flex: 1, display: 'flex', flexDirection: 'column', gap: '22px' }}>
          
          {/* BANNER DE ADVERTENCIA SI NO ES VÁLIDO */}
          {!isValid && (
            <div style={{ background: 'rgba(255,71,87,0.08)', border: '1px solid rgba(255,71,87,0.25)', borderRadius: '14px', padding: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{ fontSize: '16px' }}>🚨</span>
                <span style={{ color: '#FF4757', fontWeight: 900, fontSize: '13px', textTransform: 'uppercase' }}>
                  Compuerta de Seguridad Activa — Faltan Variables Requeridas
                </span>
              </div>
              <p style={{ margin: '0 0 10px 0', fontSize: '12px', color: '#BBB', lineHeight: '1.4' }}>
                El protocolo de eTrade requiere que el 100% de los parámetros estén presentes sin valores nulos ni en blanco. Si alguna variable crítica falta durante la operación, el monitor cerrará la posición inmediatamente para proteger el capital.
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                {missing.map((f: string, i: number) => (
                  <span key={i} style={{ background: 'rgba(255,71,87,0.2)', color: '#FF7675', border: '1px solid rgba(255,71,87,0.3)', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 800 }}>
                    ❌ {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 1. GESTIÓN DE RIESGO Y SALIDAS */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <span style={{ color: '#FFF', fontSize: '13px', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                🛡️ 1. Gestión de Riesgo & Salidas
              </span>
              <span style={{ fontSize: '11px', color: '#777' }}>Auditoría de Niveles Críticos</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
              
              {/* STOP LOSS */}
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '12px', padding: '14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '10px', color: '#777', fontWeight: 800, textTransform: 'uppercase' }}>Stop Loss (SL)</span>
                  <span style={{ fontSize: '9px', fontWeight: 900, color: risk.stop_loss > 0 ? '#00C896' : '#FF4757' }}>
                    {risk.stop_loss > 0 ? '✓ DEFINIDO' : '❌ EN BLANCO'}
                  </span>
                </div>
                <div style={{ margin: '6px 0', fontSize: '20px', fontWeight: 900, color: risk.stop_loss > 0 ? '#FF4757' : '#777' }}>
                  {risk.stop_loss > 0 ? `$${risk.stop_loss.toFixed(2)}` : '❌ EN BLANCO'}
                </div>
                <span style={{ fontSize: '11px', color: '#AAA' }}>
                  {risk.stop_loss > 0 ? `${risk.stop_loss_pct > 0 ? '+' : ''}${risk.stop_loss_pct?.toFixed(2)}% vs entrada` : 'Sin nivel de protección'}
                </span>
              </div>

              {/* TRAILING STOP */}
              <div style={{ 
                background: risk.trailing_stop > 0 ? 'rgba(255,183,77,0.04)' : 'rgba(255,71,87,0.06)', 
                border: `1px solid ${risk.trailing_stop > 0 ? 'rgba(255,183,77,0.2)' : 'rgba(255,71,87,0.3)'}`, 
                borderRadius: '12px', padding: '14px' 
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '10px', color: '#FFB74D', fontWeight: 800, textTransform: 'uppercase' }}>Trailing Stop</span>
                  <span style={{ fontSize: '9px', fontWeight: 900, color: risk.trailing_stop > 0 ? '#00C896' : '#FF4757' }}>
                    {risk.trailing_stop > 0 ? '✓ ACTIVO' : '❌ EN BLANCO'}
                  </span>
                </div>
                <div style={{ margin: '6px 0', fontSize: '20px', fontWeight: 900, color: risk.trailing_stop > 0 ? '#FFB74D' : '#FF4757' }}>
                  {risk.trailing_stop > 0 ? `$${risk.trailing_stop.toFixed(2)}` : '❌ EN BLANCO'}
                </div>
                <span style={{ fontSize: '11px', color: '#AAA' }}>
                  {risk.trailing_stop > 0 ? `${risk.trailing_stop_pct > 0 ? '+' : ''}${risk.trailing_stop_pct?.toFixed(2)}% piso ganancia` : 'Obligatorio no nulo'}
                </span>
              </div>

              {/* TAKE PROFIT */}
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '12px', padding: '14px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '10px', color: '#777', fontWeight: 800, textTransform: 'uppercase' }}>Take Profit (TP)</span>
                  <span style={{ fontSize: '9px', fontWeight: 900, color: risk.take_profit > 0 ? '#00C896' : '#FF4757' }}>
                    {risk.take_profit > 0 ? '✓ DEFINIDO' : '❌ EN BLANCO'}
                  </span>
                </div>
                <div style={{ margin: '6px 0', fontSize: '20px', fontWeight: 900, color: risk.take_profit > 0 ? '#00C896' : '#777' }}>
                  {risk.take_profit > 0 ? `$${risk.take_profit.toFixed(2)}` : '❌ EN BLANCO'}
                </div>
                <span style={{ fontSize: '11px', color: '#AAA' }}>
                  {risk.take_profit > 0 ? `+${risk.take_profit_pct?.toFixed(2)}% objetivo` : 'Sin objetivo definido'}
                </span>
              </div>

            </div>
          </div>

          {/* 2. MEDIAS MÓVILES (EMAs) */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <span style={{ color: '#FFF', fontSize: '13px', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                📈 2. Medias Móviles Exponenciales (15m)
              </span>
              <span style={{ fontSize: '11px', color: '#777' }}>Gatillo & Tendencia</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
              {[
                { name: 'EMA3', val: emas.ema_3, desc: 'Ultra-Rápida' },
                { name: 'EMA9', val: emas.ema_9, desc: 'Dinámica' },
                { name: 'EMA20', val: emas.ema_20, desc: 'Tendencia Corta' },
                { name: 'EMA50', val: emas.ema_50, desc: 'Intermedia' },
                { name: 'EMA200', val: emas.ema_200, desc: 'Estructural' },
              ].map((item, idx) => {
                const diff = item.val > 0 && curPrice > 0 ? ((curPrice - item.val) / item.val * 100) : null
                const isAbove = (diff || 0) >= 0
                return (
                  <div key={idx} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '10px', padding: '12px 10px', textAlign: 'center' }}>
                    <span style={{ fontSize: '11px', fontWeight: 900, color: '#4FC3F7' }}>{item.name}</span>
                    <div style={{ fontSize: '15px', fontWeight: 900, margin: '4px 0', color: item.val > 0 ? '#FFF' : '#FF4757' }}>
                      {item.val > 0 ? `$${item.val.toFixed(2)}` : '❌ NULO'}
                    </div>
                    {diff !== null && (
                      <span style={{ fontSize: '10px', fontWeight: 700, color: isAbove ? '#00C896' : '#FF4757' }}>
                        {isAbove ? '▲ +' : '▼ '}{diff.toFixed(1)}%
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* 3. BANDAS DE BOLLINGER & VOLATILIDAD */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <span style={{ color: '#FFF', fontSize: '13px', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                🌊 3. Bandas de Bollinger & Volatilidad
              </span>
              <span style={{ fontSize: '11px', color: '#777' }}>Canal 20, 2σ</span>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px' }}>
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '10px', padding: '12px', textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: '#777', fontWeight: 800 }}>BB SUPERIOR</span>
                <div style={{ fontSize: '16px', fontWeight: 900, color: bollinger.bb_upper > 0 ? '#00C896' : '#FF4757', marginTop: '4px' }}>
                  {bollinger.bb_upper > 0 ? `$${bollinger.bb_upper.toFixed(2)}` : '❌ NULO'}
                </div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '10px', padding: '12px', textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: '#777', fontWeight: 800 }}>BASIS (MEDIA)</span>
                <div style={{ fontSize: '16px', fontWeight: 900, color: bollinger.basis > 0 ? '#FFB74D' : '#FF4757', marginTop: '4px' }}>
                  {bollinger.basis > 0 ? `$${bollinger.basis.toFixed(2)}` : '❌ NULO'}
                </div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '10px', padding: '12px', textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: '#777', fontWeight: 800 }}>BB INFERIOR</span>
                <div style={{ fontSize: '16px', fontWeight: 900, color: bollinger.bb_lower > 0 ? '#FF4757' : '#FF4757', marginTop: '4px' }}>
                  {bollinger.bb_lower > 0 ? `$${bollinger.bb_lower.toFixed(2)}` : '❌ NULO'}
                </div>
              </div>
              <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '10px', padding: '12px', textAlign: 'center' }}>
                <span style={{ fontSize: '10px', color: '#777', fontWeight: 800 }}>ATR (14)</span>
                <div style={{ fontSize: '16px', fontWeight: 900, color: bollinger.atr > 0 ? '#4FC3F7' : '#777', marginTop: '4px' }}>
                  {bollinger.atr > 0 ? `$${bollinger.atr.toFixed(2)}` : '—'}
                </div>
              </div>
            </div>
          </div>

          {/* 4. BANDAS FIBONACCI (1 AL 6) */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
              <span style={{ color: '#FFF', fontSize: '13px', fontWeight: 900, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                🌀 4. Bandas Fibonacci de Extensión (1 al 6)
              </span>
              <span style={{ fontSize: '11px', color: '#777' }}>Zona Actual: {diag.current_zone !== 0 ? (diag.current_zone > 0 ? `U${diag.current_zone}` : `L${Math.abs(diag.current_zone)}`) : 'Basis'}</span>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
              
              {/* ALCISTA: UPPER 1 AL 6 */}
              <div style={{ background: 'rgba(0,200,150,0.02)', border: '1px solid rgba(0,200,150,0.1)', borderRadius: '12px', padding: '14px' }}>
                <span style={{ fontSize: '11px', fontWeight: 900, color: '#00C896', textTransform: 'uppercase' }}>Zona Alcista (Upper 1..6)</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
                  {[6, 5, 4, 3, 2, 1].map(idx => {
                    const val = fib[`upper_${idx}`]
                    const isZone = diag.current_zone === idx
                    return (
                      <div key={idx} style={{ 
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '4px 8px', borderRadius: '6px',
                        background: isZone ? 'rgba(0,200,150,0.15)' : 'rgba(255,255,255,0.01)',
                        border: isZone ? '1px solid #00C896' : '1px solid transparent'
                      }}>
                        <span style={{ fontSize: '11px', fontWeight: 800, color: isZone ? '#00C896' : '#AAA' }}>UPPER_{idx}</span>
                        <span style={{ fontSize: '12px', fontWeight: 900, color: val > 0 ? '#FFF' : '#FF4757', fontFamily: 'monospace' }}>
                          {val > 0 ? `$${val.toFixed(2)}` : '❌ NULO'}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* BAJISTA: LOWER 1 AL 6 */}
              <div style={{ background: 'rgba(255,71,87,0.02)', border: '1px solid rgba(255,71,87,0.1)', borderRadius: '12px', padding: '14px' }}>
                <span style={{ fontSize: '11px', fontWeight: 900, color: '#FF7675', textTransform: 'uppercase' }}>Zona Bajista (Lower 1..6)</span>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '8px' }}>
                  {[1, 2, 3, 4, 5, 6].map(idx => {
                    const val = fib[`lower_${idx}`]
                    const isZone = diag.current_zone === -idx
                    return (
                      <div key={idx} style={{ 
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '4px 8px', borderRadius: '6px',
                        background: isZone ? 'rgba(255,71,87,0.15)' : 'rgba(255,255,255,0.01)',
                        border: isZone ? '1px solid #FF4757' : '1px solid transparent'
                      }}>
                        <span style={{ fontSize: '11px', fontWeight: 800, color: isZone ? '#FF4757' : '#AAA' }}>LOWER_{idx}</span>
                        <span style={{ fontSize: '12px', fontWeight: 900, color: val > 0 ? '#FFF' : '#FF4757', fontFamily: 'monospace' }}>
                          {val > 0 ? `$${val.toFixed(2)}` : '❌ NULO'}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>

            </div>
          </div>

        </div>

        {/* FOOTER */}
        <div style={{ padding: '18px 30px', background: 'rgba(255,255,255,0.02)', borderTop: '1px solid rgba(255,255,255,0.05)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <button 
            onClick={onRefresh}
            disabled={refreshing}
            style={{ 
              background: 'rgba(56,189,248,0.1)', border: '1px solid rgba(56,189,248,0.3)',
              color: '#38BDF8', padding: '10px 18px', borderRadius: '10px',
              fontWeight: 800, fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '8px'
            }}
          >
            {refreshing ? '⏳ Recalculando...' : '🔄 Forzar Re-cálculo en Vivo'}
          </button>
          
          <button 
            onClick={onClose} 
            style={{ 
              background: '#00C896', border: 'none', color: '#000', 
              padding: '10px 24px', borderRadius: '10px', fontWeight: 900, 
              fontSize: '12px', cursor: 'pointer' 
            }}
          >
            ENTENDIDO
          </button>
        </div>

      </div>
    </div>
  )
}



