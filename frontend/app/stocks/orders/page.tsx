"use client"
import { useState, useEffect } from 'react'
import Link from 'next/link'

export default function StocksOrders() {
  const [orders, setOrders] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchOrders()
    const interval = setInterval(fetchOrders, 10000)
    return () => clearInterval(interval)
  }, [])

  const fetchOrders = async () => {
    try {
      const res = await fetch('/api/v1/stocks/orders')
      const data = await res.json()
      setOrders(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'filled': return '#00C896';
      case 'pending': return '#FFB74D';
      case 'cancelled': return '#FF4757';
      case 'expired': return '#666';
      default: return '#AAA';
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'filled': return '✅';
      case 'pending': return '⏳';
      case 'cancelled': return '❌';
      case 'expired': return '⏰';
      default: return '•';
    }
  }

  return (
    <div style={{ padding: '30px', background: '#0B0E14', minHeight: '100vh', color: '#FFF', fontFamily: 'Inter, sans-serif' }}>
      <div style={{ marginBottom: '30px' }}>
        <h1 style={{ fontSize: '24px', fontWeight: 900, margin: 0, letterSpacing: '-0.02em' }}>📜 Historial de Órdenes</h1>
        <p style={{ color: '#666', fontSize: '14px', marginTop: '5px' }}>Registro de ejecuciones MARKET y LIMIT</p>
      </div>

      <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)', overflow: 'hidden' }}>
        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: '150px 80px 80px 80px 100px 100px 100px 150px', 
          padding: '16px 24px', 
          background: 'rgba(255,255,255,0.03)',
          fontSize: '10px', 
          fontWeight: 900, 
          color: '#555', 
          textTransform: 'uppercase',
          letterSpacing: '0.1em'
        }}>
          <span>Fecha/Hora</span>
          <span>Ticker</span>
          <span>Tipo</span>
          <span>Dir</span>
          <span>Status</span>
          <span>Precio</span>
          <span>Shares</span>
          <span>Regla</span>
        </div>

        {loading && <div style={{ padding: '60px', textAlign: 'center', color: '#444' }}>Cargando órdenes...</div>}
        {!loading && orders.length === 0 && <div style={{ padding: '60px', textAlign: 'center', color: '#444' }}>No se han registrado órdenes aún.</div>}
        
        {!loading && orders.map((order, i) => (
          <div key={order.id} style={{ 
            display: 'grid', 
            gridTemplateColumns: '150px 80px 80px 80px 100px 100px 100px 150px', 
            padding: '16px 24px', 
            borderBottom: '1px solid rgba(255,255,255,0.02)',
            alignItems: 'center',
            background: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)',
            opacity: order.status === 'cancelled' || order.status === 'expired' ? 0.6 : 1
          }}>
            <span style={{ fontSize: '11px', color: '#666' }}>
              {new Date(order.created_at).toLocaleString([], { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
            </span>
            <span style={{ fontWeight: 900 }}>{order.ticker}</span>
            <span style={{ 
              fontSize: '10px', 
              fontWeight: 800, 
              color: order.order_type === 'market' ? '#4FC3F7' : '#FFB74D',
            }}>
              {order.order_type.toUpperCase()}
            </span>
            <span style={{ 
              fontWeight: 800, 
              color: order.direction === 'buy' ? '#00C896' : '#FF4757' 
            }}>
              {order.direction.toUpperCase()}
            </span>
            <span style={{ 
              fontSize: '11px', 
              fontWeight: 700, 
              color: getStatusColor(order.status),
              display: 'flex',
              alignItems: 'center',
              gap: '6px'
            }}>
              {getStatusIcon(order.status)} {order.status.toUpperCase()}
            </span>
            <span style={{ fontWeight: 700 }}>
              ${order.filled_price ? order.filled_price.toFixed(2) : (order.limit_price ? order.limit_price.toFixed(2) : order.market_price?.toFixed(2))}
            </span>
            <span style={{ color: '#AAA' }}>{order.shares || '—'}</span>
            <span style={{ fontSize: '10px', color: '#555', fontFamily: 'monospace' }}>
              {order.rule_code}
            </span>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '30px' }}>
        <Link href="/stocks/positions" style={{ color: '#00C896', textDecoration: 'none', fontWeight: 800, fontSize: '12px' }}>
          ← IR AL PORTAFOLIO DE POSICIONES
        </Link>
      </div>
    </div>
  )
}
