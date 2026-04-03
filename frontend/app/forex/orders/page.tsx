'use client'
import { useState, useEffect } from 'react'
import ForexWelcomeScreen from '../WelcomeScreen'

export default function ForexOrders() {
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/v1/forex/status')
      .then(r => r.json())
      .then(d => {
          setConnected(d.connected)
          setLoading(false)
      })
  }, [])

  if (loading) return null

  if (!connected) {
    return <ForexWelcomeScreen />
  }

  return (
    <div style={{ padding:'24px' }}>
      <h1 style={{ color:'#FFF', fontSize: '24px', fontWeight: 900, fontStyle: 'italic' }}>💱 Forex Pending Orders</h1>
      <p style={{ color: '#555', marginTop: '10px' }}>Vista previa de órdenes pendientes en IC Markets.</p>
    </div>
  )
}
