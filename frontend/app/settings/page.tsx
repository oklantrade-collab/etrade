'use client'
import { useState, useEffect } from 'react'
import { supabase } from '@/lib/supabase'
import RuleEngineModal from '@/components/RuleEngineModal'

const TABS = [
  { key: 'crypto', label: '🔶 Crypto', subtitle: 'Binance Futures' },
  { key: 'forex',  label: '💱 Forex',  subtitle: 'IC Markets' },
  { key: 'system', label: '⚙️ Sistema', subtitle: 'General' },
]

export default function SettingsPage() {
  const [activeTab, setActiveTab] = useState('crypto')
  const [config, setConfig] = useState<any>(null)
  const [saved, setSaved] = useState(false)
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    const { data: tc } = await supabase.from('trading_config').select('*').single()
    const { data: rc } = await supabase.from('risk_config').select('*').single()
    if (tc && rc) {
      setConfig({ ...tc, ...rc })
    } else if (tc) {
      setConfig(tc)
    }
  }

  const handleSave = async (section: string, data: any) => {
    const tradingFields = [
      'capital_total', 'capital_crypto_futures', 'leverage_crypto', 
      'min_profit_exit_pct', 'exit_on_signal_reversal', 'use_strategy_engine_v2',
      'capital_forex_futures', 'leverage_forex', 'telegram_enabled', 'ai_enabled', 'ai_mode',
      'telegram_bot_token', 'telegram_chat_id', 'paper_trading', 'regime_params'
    ]
    
    const riskFields = [
      'max_risk_per_trade_pct', 'max_open_trades', 'max_positions_per_symbol'
    ]

    const toUpdateTC: any = {}
    const toUpdateRC: any = {}

    // Procesar MTF thresholds específicos si vienen de la pestaña sistema
    if (data.mtf_bajo !== undefined) {
      const currentRegimeParams = config.regime_params || {};
      toUpdateTC.regime_params = {
        ...currentRegimeParams,
        bajo_riesgo: { ...currentRegimeParams.bajo_riesgo, mtf_threshold: data.mtf_bajo },
        riesgo_medio: { ...currentRegimeParams.riesgo_medio, mtf_threshold: data.mtf_medio },
        alto_riesgo: { ...currentRegimeParams.alto_riesgo, mtf_threshold: data.mtf_alto },
      }
    }

    Object.keys(data).forEach(key => {
      if (['mtf_bajo', 'mtf_medio', 'mtf_alto'].includes(key)) return; // Ya procesado arriba
      if (tradingFields.includes(key)) toUpdateTC[key] = data[key]
      if (riskFields.includes(key)) toUpdateRC[key] = data[key]
      if (!tradingFields.includes(key) && !riskFields.includes(key)) toUpdateTC[key] = data[key]
    })

    try {
      if (Object.keys(toUpdateTC).length > 0) {
        await supabase.from('trading_config').update(toUpdateTC).eq('id', 1)
      }
      if (Object.keys(toUpdateRC).length > 0) {
        await supabase.from('risk_config').update(toUpdateRC).eq('id', 1)
      }
      
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      loadConfig()
    } catch (err) {
      console.error("Error saving config:", err)
      alert("Error al guardar la configuración")
    }
  }

  return (
    <div style={{ padding: '32px', maxWidth: '900px', margin: '0 auto' }}>
      {/* HEADER */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: '#FFF', margin: 0 }}>⚙️ Configuración</h1>
          <p style={{ color: '#555', fontSize: '13px', marginTop: '4px' }}>
            {new Date().toLocaleDateString('es-PE', { day:'numeric', month:'long', year:'numeric' })}
          </p>
        </div>
        {saved && (
          <div style={{ background: 'rgba(0,200,150,0.15)', border: '1px solid #00C896', borderRadius:'8px', padding: '8px 16px', color: '#00C896', fontSize: '13px' }}>
            ✓ Guardado correctamente
          </div>
        )}
      </div>

      {/* TABS */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '24px', background: 'rgba(255,255,255,0.03)', padding: '4px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
        {TABS.map(tab => (
          <button key={tab.key} onClick={() => setActiveTab(tab.key)} style={{
            flex: 1, padding: '10px 16px', borderRadius: '7px', border: 'none',
            background: activeTab === tab.key ? 'rgba(255,255,255,0.08)' : 'transparent',
            color: activeTab === tab.key ? '#FFF' : '#555',
            cursor: 'pointer', fontSize: '13px', fontWeight: activeTab === tab.key ? 600 : 400,
            transition: 'all 0.2s',
          }}>
            {tab.label}
            <div style={{ fontSize: '10px', color: activeTab === tab.key ? '#666' : '#444', marginTop: '2px' }}>{tab.subtitle}</div>
          </button>
        ))}
      </div>

      {/* CONTENIDO */}
      {activeTab === 'crypto' && config && (
        <CryptoSettings config={config} onSave={(data: any) => handleSave('crypto', data)} />
      )}
      {activeTab === 'forex' && config && (
        <ForexSettings config={config} onSave={(data: any) => handleSave('forex', data)} />
      )}
      {activeTab === 'system' && config && (
        <SystemSettings config={config} onSave={(data: any) => handleSave('system', data)} onOpenRules={() => setIsRuleModalOpen(true)} />
      )}

      <RuleEngineModal isOpen={isRuleModalOpen} onClose={() => setIsRuleModalOpen(false)} />
    </div>
  )
}

/* ════════════════════════════════════════════════
   COMPONENTE CryptoSettings 
   ════════════════════════════════════════════════ */

const CryptoSettings = ({ config, onSave }: any) => {
  const [form, setForm] = useState({
    capital_crypto_futures: config.capital_crypto_futures || 500,
    leverage_crypto: config.leverage_crypto || 5,
    max_risk_per_trade_pct: config.max_risk_per_trade_pct || 1.0,
    max_open_trades: config.max_open_trades || 3,
    min_profit_exit_pct: config.min_profit_exit_pct || 0.30,
    exit_on_signal_reversal: config.exit_on_signal_reversal ?? true,
    use_strategy_engine_v2: config.use_strategy_engine_v2 ?? true,
  })

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
      <StatusBadge label="Binance Futures" status="ACTIVO" color="#F7931A" detail="Paper Trading" />
      <SettingsSection title="💰 Capital">
        <SettingRow label="Capital asignado" hint="USD disponible para trading" value={form.capital_crypto_futures} type="number" prefix="$" onChange={(v: any) => setForm({ ...form, capital_crypto_futures: v })} />
        <SettingRow label="Apalancamiento" hint="Multiplicador de posición" value={form.leverage_crypto} type="number" suffix="x" min={1} max={20} onChange={(v: any) => setForm({ ...form, leverage_crypto: v })} />
      </SettingsSection>
      <SettingsSection title="🛡️ Gestión de Riesgo">
        <SettingRow label="Riesgo por trade" hint="% del capital máximo por operación" value={form.max_risk_per_trade_pct} type="number" suffix="%" step={0.1} min={0.1} max={5} onChange={(v: any) => setForm({ ...form, max_risk_per_trade_pct: v })} />
        <SettingRow label="Máximo posiciones simultáneas" hint="Límite de trades abiertos al mismo tiempo" value={form.max_open_trades} type="number" min={1} max={10} onChange={(v: any) => setForm({ ...form, max_open_trades: v })} />
        <SettingRow label="Ganancia mínima para salida" hint="% mínimo antes de cerrar por señal" value={form.min_profit_exit_pct} type="number" suffix="%" step={0.1} min={0} max={5} onChange={(v: any) => setForm({ ...form, min_profit_exit_pct: v })} />
      </SettingsSection>
      <SettingsSection title="🧠 Strategy Engine">
        <SettingToggle label="Motor v2 (IA Rules)" hint="Usar el Strategy Engine v1.0 con reglas dinámicas" value={form.use_strategy_engine_v2} onChange={(v: any) => setForm({ ...form, use_strategy_engine_v2: v })} />
        <SettingToggle label="Salida por reversión de señal" hint="Cerrar posición cuando la señal cambia de dirección" value={form.exit_on_signal_reversal} onChange={(v: any) => setForm({ ...form, exit_on_signal_reversal: v })} />
      </SettingsSection>
      <SettingsSection title="📊 Símbolos Activos">
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', padding: '8px 18px' }}>
          {['BTCUSDT','ETHUSDT', 'SOLUSDT','ADAUSDT'].map(sym => (
            <div key={sym} style={{ padding: '6px 14px', background: 'rgba(247,147,26,0.10)', border: '1px solid rgba(247,147,26,0.25)', borderRadius: '6px', color: '#F7931A', fontSize: '12px', fontWeight: 600 }}>● {sym}</div>
          ))}
        </div>
      </SettingsSection>
      <SaveButton onSave={() => onSave(form)} />
    </div>
  )
}

/* ════════════════════════════════════════════════
   COMPONENTE ForexSettings 
   ════════════════════════════════════════════════ */

const ForexSettings = ({ config, onSave }: any) => {
  const [form, setForm] = useState({
    capital_forex_futures: config.capital_forex_futures || 0,
    leverage_forex: config.leverage_forex || 30,
    forex_risk_per_trade_pct: 1.0,
    forex_sl_pips:            20,
    forex_tp_pips:            40,
    forex_max_positions:      3,
    forex_active: false,
    pairs_active: { EURUSD: true, GBPUSD: true, USDJPY: false, XAUUSD: true },
    sessions_active: { london: true, new_york: true, asian: false, overnight: false }
  })
  const isConnected = config.capital_forex_futures > 0
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
      <StatusBadge label="IC Markets / cTrader" status={isConnected ? 'ACTIVO' : 'SPRINT 3'} color={isConnected ? '#00C896' : '#555'} detail={isConnected ? 'Conectado' : 'Credenciales pendientes'} />
      {!isConnected && (
        <div style={{ background: 'rgba(255,183,77,0.08)', border: '1px solid rgba(255,183,77,0.20)', borderRadius: '8px', padding: '16px', color: '#FFB74D', fontSize: '13px' }}>
          <div style={{ fontWeight:700, marginBottom:'8px' }}>📋 Para activar Forex:</div>
          <ol style={{ margin:0, paddingLeft:'20px', lineHeight:'1.8' }}>
            <li>Obtener credenciales en <a href="https://openapi.ctrader.com" target="_blank" style={{ color:'#4FC3F7', marginLeft:'4px' }}>openapi.ctrader.com</a></li>
            <li>Agregar al .env: CTRADER_CLIENT_ID, CTRADER_CLIENT_SECRET, CTRADER_ACCOUNT_ID, CTRADER_ACCESS_TOKEN</li>
            <li>Ejecutar: python test_ctrader_connection.py</li>
            <li>Activar desde este panel una vez conectado</li>
          </ol>
        </div>
      )}
      <SettingsSection title="💰 Capital Forex">
        <SettingRow label="Capital asignado" hint="USD disponible para Forex" value={form.capital_forex_futures} type="number" prefix="$" disabled={!isConnected} onChange={(v: any) => setForm({ ...form, capital_forex_futures: v })} />
        <SettingRow label="Apalancamiento" hint="IC Markets ofrece hasta 30:1 (ASIC regulado)" value={form.leverage_forex} type="number" suffix="x" min={1} max={30} disabled={!isConnected} onChange={(v: any) => setForm({ ...form, leverage_forex: v })} />
      </SettingsSection>
      <SettingsSection title="🛡️ Gestión de Riesgo">
        <SettingRow label="Riesgo por trade" value={form.forex_risk_per_trade_pct} type="number" suffix="%" step={0.1} min={0.1} max={3} disabled={!isConnected} onChange={(v: any) => setForm({ ...form, forex_risk_per_trade_pct: v })} />
        <SettingRow label="Stop Loss (pips)" hint="Distancia del SL en pips" value={form.forex_sl_pips} type="number" suffix="pips" min={5} max={100} disabled={!isConnected} onChange={(v: any) => setForm({ ...form, forex_sl_pips: v })} />
        <SettingRow label="Take Profit (pips)" hint="Objetivo en pips (RR mínimo 1:2)" value={form.forex_tp_pips} type="number" suffix="pips" min={10} max={200} disabled={!isConnected} onChange={(v: any) => setForm({ ...form, forex_tp_pips: v })} />
      </SettingsSection>
      <SettingsSection title="💱 Pares de Divisas">
        <div style={{ display:'grid', gridTemplateColumns: '1fr 1fr', gap:'8px', padding: '8px 18px' }}>
          {Object.entries(form.pairs_active).map(([pair, active]: any) => {
            const PAIRS_INFO: Record<string, any> = { 
              EURUSD: { name:'Euro / USD', flag:'🇪🇺🇺🇸', pip:'0.0001' }, 
              GBPUSD: { name:'GBP / USD', flag:'🇬🇧🇺🇸', pip:'0.0001' }, 
              USDJPY: { name:'USD / JPY', flag:'🇺🇸🇯🇵', pip:'0.01' }, 
              XAUUSD: { name:'Oro / USD', flag:'🥇🇺🇸', pip:'0.01' } 
            }
            const info = PAIRS_INFO[pair]
            return (
              <div key={pair} onClick={() => isConnected && setForm({ ...form, pairs_active: { ...form.pairs_active, [pair]: !active } })} style={{
                padding: '12px', borderRadius:'8px', border: `1px solid ${active ? 'rgba(0,200,150,0.30)' : 'rgba(255,255,255,0.06)'}`,
                background: active ? 'rgba(0,200,150,0.06)' : 'rgba(255,255,255,0.02)', cursor: isConnected ? 'pointer' : 'not-allowed', opacity: isConnected ? 1 : 0.5,
              }}>
                <div style={{ display: 'flex', justifyContent:'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '14px', fontWeight:700, color: active ? '#00C896' : '#666' }}>{info?.flag} {pair}</span>
                  <div style={{ width: '14px', height: '14px', borderRadius: '50%', background: active ? '#00C896' : 'rgba(255,255,255,0.10)', border: `2px solid ${active ? '#00C896' : '#333'}` }} />
                </div>
                <div style={{ fontSize: '11px', color: '#555', marginTop: '4px' }}>{info?.name} · pip {info?.pip}</div>
              </div>
            )
          })}
        </div>
      </SettingsSection>
      <SaveButton onSave={() => onSave(form)} disabled={!isConnected} disabledMessage="Conectar IC Markets primero" />
    </div>
  )
}

/* ════════════════════════════════════════════════
   COMPONENTE SystemSettings
   ════════════════════════════════════════════════ */

const SystemSettings = ({ config, onSave, onOpenRules }: any) => {
  const [form, setForm] = useState({
    telegram_enabled: config.telegram_enabled ?? true,
    ai_enabled: config.ai_enabled ?? true,
    ai_mode: config.ai_mode || 'informative',
    paper_trading: config.paper_trading ?? true,
    // MTF Thresholds
    mtf_bajo:  config.regime_params?.bajo_riesgo?.mtf_threshold || 0.50,
    mtf_medio: config.regime_params?.riesgo_medio?.mtf_threshold || 0.65,
    mtf_alto:  config.regime_params?.alto_riesgo?.mtf_threshold || 0.80,
  })

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
      <SettingsSection title="📱 Alertas y Notificaciones">
        <SettingToggle label="Telegram Activado" hint="Recibir notificaciones de trades" value={form.telegram_enabled} onChange={(v: any) => setForm({ ...form, telegram_enabled: v })} />
      </SettingsSection>

      <SettingsSection title="🛡️ Filtros de Riesgo Global (MTF)">
        <div style={{ padding: '8px 18px' }}>
          <p style={{ color: '#555', fontSize: '11px', marginBottom: '12px' }}>Define el Ratio MTF Score mínimo necesario para permitir aperturas según el régimen actual.</p>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', marginBottom: '8px' }}>
            <ThresholdInput label="🟢 Bajo Riesgo" value={form.mtf_bajo} onChange={(v: any) => setForm({ ...form, mtf_bajo: v })} />
            <ThresholdInput label="🟡 Medio" value={form.mtf_medio} onChange={(v: any) => setForm({ ...form, mtf_medio: v })} />
            <ThresholdInput label="🔴 Alto Riesgo" value={form.mtf_alto} onChange={(v: any) => setForm({ ...form, mtf_alto: v })} />
          </div>
        </div>
      </SettingsSection>

      <SettingsSection title="🤖 Inteligencia Artificial">
        <SettingToggle label="IA Análisis Activada" hint="Claude analiza sentimiento y confirma spikes" value={form.ai_enabled} onChange={(v: any) => setForm({ ...form, ai_enabled: v })} />
        <SettingRow label="Modo de IA" hint="Vinculante (Binding) o Informativo" value={form.ai_mode} onChange={(v: any) => setForm({ ...form, ai_mode: v })} />
      </SettingsSection>

      <SettingsSection title="⚙️ General">
        <SettingToggle label="Modo Paper Trading" hint="Simular operaciones sin capital real" value={form.paper_trading} onChange={(v: any) => setForm({ ...form, paper_trading: v })} />
      </SettingsSection>
      
      <SettingsSection title="🧠 Algoritmo Core">
          <div style={{ padding: '12px 18px' }}>
              <button onClick={onOpenRules} style={{ width: '100%', padding: '10px', background: 'rgba(79,195,247,0.1)', border: '1px solid rgba(79,195,247,0.3)', borderRadius: '8px', color: '#4FC3F7', fontSize: '12px', fontWeight: 700, cursor: 'pointer' }}>⚙️ EDITAR REGLAS (RULE ENGINE)</button>
          </div>
      </SettingsSection>
      <SaveButton onSave={() => onSave(form)} />
    </div>
  )
}

/* ════════════════════════════════════════════════
   COMPONENTES HELPER 
   ════════════════════════════════════════════════ */

const ThresholdInput = ({ label, value, onChange }: any) => (
  <div style={{ padding: '8px', background: 'rgba(255,255,255,0.02)', borderRadius: '6px', border: '1px solid rgba(255,255,255,0.05)' }}>
    <div style={{ fontSize: '10px', color: '#555', fontWeight: 700, marginBottom: '6px', textTransform: 'uppercase' }}>{label}</div>
    <input type="number" step="0.05" value={value} onChange={(e) => onChange(parseFloat(e.target.value))} style={{ width: '100%', background: 'transparent', border: 'none', color: '#FFF', fontSize: '16px', fontWeight: 700, outline: 'none' }} />
  </div>
)

const StatusBadge = ({ label, status, color, detail }: any) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '14px 18px', background: `rgba(${color === '#F7931A' ? '247,147,26' : color === '#00C896' ? '0,200,150' : '255,255,255'}, 0.05)`, borderRadius: '10px', border: `1px solid ${color}22` }}>
    <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: color, boxShadow: `0 0 8px ${color}` }} />
    <div><span style={{ color: '#FFF', fontWeight:700, fontSize: '14px' }}>{label}</span><span style={{ color: '#555', fontSize: '12px', marginLeft:'8px' }}>{detail}</span></div>
    <div style={{ marginLeft: 'auto', padding: '4px 12px', borderRadius: '20px', background: `${color}22`, border: `1px solid ${color}44`, color: color, fontSize: '11px', fontWeight: 700, letterSpacing:'1px' }}>{status}</div>
  </div>
)

const SettingsSection = ({ title, children }: any) => (
  <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '10px', overflow: 'hidden' }}>
    <div style={{ padding: '12px 18px', borderBottom: '1px solid rgba(255,255,255,0.04)', color: '#888', fontSize: '11px', fontWeight: 700, letterSpacing:'1.5px', textTransform: 'uppercase' }}>{title}</div>
    <div style={{ padding:'8px 0' }}>{children}</div>
  </div>
)

const SettingRow = ({ label, hint, value, type, prefix, suffix, step, min, max, disabled, onChange }: any) => (
  <div style={{ display: 'flex', alignItems: 'center', padding: '10px 18px', gap: '16px', opacity: disabled ? 0.5 : 1 }}>
    <div style={{ flex:1 }}><div style={{ color: '#CCC', fontSize: '13px' }}>{label}</div>{hint && <div style={{ color: '#555', fontSize: '11px', marginTop: '2px' }}>{hint}</div>}</div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      {prefix && <span style={{ color:'#555', fontSize:'13px' }}>{prefix}</span>}
      <input type={type || 'text'} value={value} step={step} min={min} max={max} disabled={disabled} onChange={e => onChange(type === 'number' ? parseFloat(e.target.value) : e.target.value)} style={{ width: '100px', padding: '6px 10px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.10)', borderRadius: '6px', color: '#FFF', fontSize: '13px', textAlign: 'right' }} />
      {suffix && <span style={{ color:'#555', fontSize:'13px' }}>{suffix}</span>}
    </div>
  </div>
)

const SettingToggle = ({ label, hint, value, onChange }: any) => (
  <div style={{ display: 'flex', alignItems: 'center', padding: '10px 18px', gap: '16px' }}>
    <div style={{ flex:1 }}><div style={{ color:'#CCC', fontSize:'13px' }}>{label}</div>{hint && <div style={{ color:'#555', fontSize:'11px', marginTop:'2px' }}>{hint}</div>}</div>
    <div onClick={() => onChange(!value)} style={{ width: '44px', height: '24px', borderRadius: '12px', background: value ? '#00C896' : 'rgba(255,255,255,0.10)', position: 'relative', cursor: 'pointer', transition: 'background 0.2s' }}>
      <div style={{ position: 'absolute', top: '3px', left: value ? '23px' : '3px', width: '18px', height: '18px', borderRadius:'50%', background: '#FFF', transition: 'left 0.2s' }} />
    </div>
  </div>
)

const SaveButton = ({ onSave, disabled, disabledMessage }: any) => (
  <div style={{ padding: '8px 18px' }}>
    <button onClick={onSave} disabled={disabled} title={disabledMessage} style={{ width: '100%', padding: '14px', borderRadius: '10px', border: 'none', background: disabled ? 'rgba(255,255,255,0.05)' : 'linear-gradient(135deg, #00C896, #00A878)', color: disabled ? '#444' : '#000', fontSize: '14px', fontWeight: 700, cursor: disabled ? 'not-allowed' : 'pointer', letterSpacing:'0.5px' }}>{disabled ? (disabledMessage || 'No disponible') : '💾 Guardar Configuración'}</button>
  </div>
)
