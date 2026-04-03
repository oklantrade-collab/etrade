'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

export default function RiskPage() {
  const [riskConfig, setRiskConfig] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadRiskConfig()
  }, [])

  async function loadRiskConfig() {
    setLoading(true)
    const { data } = await supabase.from('risk_config').select('*').limit(1).single()
    if (data) {
      setRiskConfig(data)
    }
    setLoading(false)
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!riskConfig) return
    
    // Convert string inputs to floats before sending
    const updateData = {
      max_risk_per_trade_pct: parseFloat(riskConfig.max_risk_per_trade_pct),
      max_daily_loss_pct: parseFloat(riskConfig.max_daily_loss_pct),
      max_open_trades: parseInt(riskConfig.max_open_trades),
      max_positions_per_symbol: parseInt(riskConfig.max_positions_per_symbol || 3),
      sl_multiplier: parseFloat(riskConfig.sl_multiplier),
      rr_ratio: parseFloat(riskConfig.rr_ratio),
      kill_switch_enabled: riskConfig.kill_switch_enabled,
      kill_switch_loss_pct: parseFloat(riskConfig.kill_switch_loss_pct),
      slippage_estimate_pct: parseFloat(riskConfig.slippage_estimate_pct),
      bot_active: riskConfig.bot_active
    }

    const { error } = await supabase.from('risk_config').update(updateData).eq('id', riskConfig.id)
    if (!error) {
       alert("Parameters updated successfully.")
       loadRiskConfig()
    } else {
       alert(`Failed to update: ${error.message}`)
    }
  }

  async function emergencyKill() {
    if (!confirm('🚨 EMERGENCY KILL SWITCH 🚨\n\nThis will immediately DEACTIVATE the bot and CLOSE ALL OPEN POSITIONS at market price.\n\nAre you absolutely sure you want to proceed?')) {
      return
    }
    
    try {
      await fetch('/api/v1/risk/kill-switch', { method: 'POST' })
      alert('KILL SWITCH ACTIVATED. Bot disabled.')
      loadRiskConfig()
    } catch (e: any) {
      alert(`Error hitting kill switch: ${e.message}`)
    }
  }

  if (loading || !riskConfig) {
     return <div className="page-header"><h1>Risk Manager</h1><p>Loading...</p></div>
  }

  return (
    <div>
      <div className="page-header">
        <h1>Risk Manager</h1>
        <p>Global portfolio protection and pipeline parameters</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 24 }}>
        
        {/* Risk Form */}
        <div className="card">
          <div className="card-header">
            <span className="card-title">Trading Parameters</span>
            <span className={`badge ${riskConfig.bot_active ? 'badge-green' : 'badge-red'}`}>
              Bot Status: {riskConfig.bot_active ? 'ACTIVE' : 'INACTIVE'}
            </span>
          </div>

          <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            
            <div className="form-grid">
              <div className="form-group">
                <label>Risk Per Trade (%)</label>
                <input 
                  type="number" step="0.1" className="input" 
                  value={riskConfig.max_risk_per_trade_pct}
                  onChange={e => setRiskConfig({...riskConfig, max_risk_per_trade_pct: e.target.value})}
                  title="Percentage of total balance risked per trade"
                />
              </div>

              <div className="form-group">
                <label>Max Open Trades (Global)</label>
                <input 
                  type="number" className="input" 
                  value={riskConfig.max_open_trades}
                  onChange={e => setRiskConfig({...riskConfig, max_open_trades: e.target.value})}
                />
              </div>

              <div className="form-group">
                <label>Max Positions Per Symbol</label>
                <input 
                  type="number" className="input" 
                  value={riskConfig.max_positions_per_symbol || 3}
                  onChange={e => setRiskConfig({...riskConfig, max_positions_per_symbol: e.target.value})}
                  title="Maximum total of Open Positions + Pending Orders allowed for a single crypto symbol"
                />
              </div>

              <div className="form-group">
                <label>Max Daily Loss (%)</label>
                <input 
                  type="number" step="0.1" className="input" 
                  value={riskConfig.max_daily_loss_pct}
                  onChange={e => setRiskConfig({...riskConfig, max_daily_loss_pct: e.target.value})}
                />
              </div>

              <div className="form-group">
                <label>Slippage Estimate (%)</label>
                <input 
                  type="number" step="0.01" className="input" 
                  value={riskConfig.slippage_estimate_pct}
                  onChange={e => setRiskConfig({...riskConfig, slippage_estimate_pct: e.target.value})}
                />
              </div>
            </div>

            <div style={{ height: 1, backgroundColor: 'var(--border-color)' }}></div>

            <div className="card-header" style={{ marginBottom: 0 }}>
              <span className="card-title">Strategy Execution (OCO)</span>
            </div>

            <div className="form-grid">
              <div className="form-group">
                <label>Stop Loss (ATR Multiplier)</label>
                <input 
                  type="number" step="0.1" className="input" 
                  value={riskConfig.sl_multiplier}
                  onChange={e => setRiskConfig({...riskConfig, sl_multiplier: e.target.value})}
                />
              </div>
              
              <div className="form-group">
                <label>Risk/Reward Ratio</label>
                <input 
                  type="number" step="0.1" className="input" 
                  value={riskConfig.rr_ratio}
                  onChange={e => setRiskConfig({...riskConfig, rr_ratio: e.target.value})}
                />
              </div>
            </div>

            <div style={{ marginTop: 16, display: 'flex', gap: 12 }}>
              <button type="submit" className="btn btn-primary">Save Configuration</button>
              <button 
                type="button" 
                className="btn btn-ghost"
                onClick={() => setRiskConfig({...riskConfig, bot_active: !riskConfig.bot_active})}
              >
                {riskConfig.bot_active ? 'Pause Bot' : 'Re-activate Bot'}
              </button>
            </div>
          </form>
        </div>

        {/* Kill Switch Panel */}
        <div className="card" style={{ display: 'flex', flexDirection: 'column', textAlign: 'center' }}>
          <div className="card-header" style={{ justifyContent: 'center' }}>
            <span className="card-title" style={{ color: 'var(--accent-red)' }}>Emergency Control</span>
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', marginTop: 32, marginBottom: 32 }}>
            <button onClick={emergencyKill} className="kill-switch-btn">
              HALT TRADING
            </button>
          </div>

          <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
            Overrides all worker loops. Closes all open positions via Binance MARKET command immediately. Deactivates automated trading.
          </div>

          <div style={{ height: 1, backgroundColor: 'var(--border-color)', margin: '20px 0' }}></div>
          
          <div className="form-group" style={{ textAlign: 'left' }}>
            <label style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', color: 'var(--text-primary)' }}>
              Auto Kill-Switch Enabled
              <input 
                type="checkbox" 
                checked={riskConfig.kill_switch_enabled} 
                onChange={e => setRiskConfig({...riskConfig, kill_switch_enabled: e.target.checked})}
                style={{ width: 18, height: 18 }}
              />
            </label>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 8 }}>
               <label>Daily Loss Level Trigger</label>
               <input 
                  type="number" style={{ width: 60, padding: '4px 8px' }} step="0.1" className="input" 
                  value={riskConfig.kill_switch_loss_pct}
                  onChange={e => setRiskConfig({...riskConfig, kill_switch_loss_pct: e.target.value})}
                />
            </div>
          </div>
        </div>

      </div>
    </div>
  )
}
