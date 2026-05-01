'use client'
import { useState, useEffect } from 'react'
import { supabase } from '@/lib/supabase'
import { useRouter } from 'next/navigation'
import RuleEngineModal from '@/components/RuleEngineModal'

const TABS = [
  { key: 'crypto', label: '🔶 Crypto', subtitle: 'Binance Futures' },
  { key: 'forex',  label: '💱 Forex',  subtitle: 'IC Markets' },
  { key: 'stocks', label: '📈 Stocks', subtitle: 'Inversiones Pro' },
  { key: 'system', label: '⚙️ Sistema', subtitle: 'General' },
]

export default function SettingsPage() {
  const router = useRouter()
  const [activeTab, setActiveTab] = useState('crypto')
  const [config, setConfig] = useState<any>(null)
  const [uSettings, setUSettings] = useState<any>({
    fg_mcap_min: 300, fg_mcap_max: 10000, fg_rev_growth_min: 25, fg_price_max: 50, fg_rs_min: 70,
    gl_mcap_min: 5000, gl_rev_growth_min: 12, gl_margin_min: 30, gl_rs_min: 75, gl_inst_min: 40, gl_price_max: 200,
    ex_vol_min: 200000, ex_debt_equity_max: 3.0, ex_eps_neg_quarters_max: 4,
    w_rev_growth: 25, w_gross_margin: 20, w_eps_growth: 20, w_rs_score: 20, w_inst_ownership: 15
  })
  const [saved, setSaved] = useState(false)
  const [stocksConfig, setStocksConfig] = useState<any>(null)
  const [isRuleModalOpen, setIsRuleModalOpen] = useState(false)
  const [isSweeping, setIsSweeping] = useState(false)

  useEffect(() => {
    loadConfig()
  }, [])

  const loadConfig = async () => {
    const { data: tc } = await supabase.from('trading_config').select('*').single()
    const { data: rc } = await supabase.from('risk_config').select('*').single()
    const { data: us_res } = await supabase.from('universe_settings').select('*').eq('id', 1).limit(1)
    const us = us_res && us_res.length > 0 ? us_res[0] : null
    
    if (tc && rc) setConfig({ ...tc, ...rc, tc_id: tc.id, rc_id: rc.id })
    if (us) setUSettings(us)

    // Load specialized stocks_config
    const { data: sc } = await supabase.from('stocks_config').select('*')
    if (sc) {
        setStocksConfig(sc.reduce((acc: any, curr: any) => ({ ...acc, [curr.key]: curr.value }), {}));
    }
  }

  const handleSave = async (section: string, data: any, shouldSweep = false) => {
    if (section === 'stocks') {
      try {
        const API = 'http://localhost:8080';
        const saveRes = await fetch(`${API}/api/v1/stocks/universe/settings`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        const resultSave = await saveRes.json();
        
        if (!saveRes.ok) {
            const msg = resultSave.detail?.message || resultSave.detail || 'Fallo desconocido';
            alert(`❌ Error del servidor: ${msg}`);
            return;
        }
        
        if (!shouldSweep) {
            alert("📊 Configuración de Stocks guardada con éxito");
            setSaved(true);
            setTimeout(() => setSaved(false), 2000);
            loadConfig();
        } else {
            setIsSweeping(true);
            const res = await fetch(`${API}/api/v1/stocks/refresh-fundamentals`, { method: 'POST' });
            const result = await res.json();
            setIsSweeping(false);
            
            if (res.ok && result.summary) {
                const s = result.summary;
                alert(`✅ Re-escaneo completo:\n- ${s.FUTURE_GIANT} FUTURE_GIANT\n- ${s.GROWTH_LEADER} GROWTH_LEADER\n- Total analizados: ${s.TOTAL}`);
                router.push('/stocks/universe');
            } else {
                alert(`❌ Error durante el re-escaneo: ${result.detail || 'Fallo desconocido'}`);
            }
        }
        return;
      } catch (err: any) {
        console.error("Error saving stocks config:", err);
        alert(`Error al guardar la configuración: ${err.message}`);
        setIsSweeping(false);
        return;
      }
    }

    if (section === 'stocks_general') {
        try {
            for (const key of Object.keys(data)) {
                await supabase.from('stocks_config').update({ value: String(data[key]) }).eq('key', key);
            }
            setSaved(true);
            // Pequeña espera para asegurar consistencia en Supabase antes de recargar
            await new Promise(resolve => setTimeout(resolve, 500));
            await loadConfig();
            setTimeout(() => setSaved(false), 2000);
            return;
        } catch (err) { 
            console.error(err); 
            alert("Error al guardar stocks_config");
            return; 
        }
    }

    // Lógica para otras pestañas (Crypto/Forex/System)
    const tradingFields = [
      'capital_total', 'capital_crypto_futures', 'leverage_crypto', 
      'min_profit_exit_pct', 'exit_on_signal_reversal', 'use_strategy_engine_v2',
      'capital_forex_futures', 'leverage_forex', 'leverage_stocks', 'pct_for_trading',
      'active_symbols', 'regime_params', 'telegram_enabled', 'ai_enabled', 'ai_mode',
      'accumulated_profit_crypto', 'accumulated_profit_forex', 'accumulated_profit_stocks',
      'telegram_bot_token', 'telegram_chat_id', 'paper_trading'
    ]
    const riskFields = ['max_risk_per_trade_pct', 'max_open_trades', 'max_positions_per_symbol', 'max_pct_per_trade']
    const toUpdateTC: any = {}
    const toUpdateRC: any = {}

    Object.keys(data).forEach(key => {
      if (tradingFields.includes(key)) toUpdateTC[key] = data[key]
      if (riskFields.includes(key)) toUpdateRC[key] = data[key]
      if (!tradingFields.includes(key) && !riskFields.includes(key)) toUpdateTC[key] = data[key]
    })

    try {
      if (Object.keys(toUpdateTC).length > 0) {
        delete toUpdateTC.id
        await supabase.from('trading_config').update(toUpdateTC).eq('id', config.tc_id || 1)
      }
      if (Object.keys(toUpdateRC).length > 0) {
        delete toUpdateRC.id
        await supabase.from('risk_config').update(toUpdateRC).eq('id', config.rc_id)
      }
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      loadConfig()
    } catch (err) {
      console.error("Error saving config:", err)
    }
  }

  return (
    <div style={{ padding: '32px', maxWidth: '900px', margin: '0 auto', opacity: isSweeping ? 0.7 : 1 }}>
      {isSweeping && (
        <div style={{ position:'fixed', top:0, left:0, right:0, bottom:0, background:'rgba(0,0,0,0.8)', zIndex:9999, display:'flex', flexDirection:'column', alignItems:'center', justifyContent:'center' }}>
            <div style={{ fontSize: '40px', marginBottom:'20px' }}>🧠</div>
            <h2 style={{ color:'#FFF', fontWeight:900, fontSize:'20px', margin:0, fontStyle:'italic' }}>Universe Sweep in Progress...</h2>
            <p style={{ color:'#555', fontSize:'13px', marginTop:'8px' }}>Modelando el futuro financiero basado en tus nuevos criterios</p>
            <div style={{ width: '240px', height:'4px', background:'rgba(255,255,255,0.05)', borderRadius:'2px', marginTop:'32px', overflow:'hidden' }}>
                <div style={{ width:'60%', height:'100%', background:'#22C55E', boxShadow: '0 0 10px #22C55E' }}></div>
            </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px' }}>
        <div>
          <h1 style={{ fontSize: '24px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>⚙️ Configuración</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: '12px', marginTop: '4px', letterSpacing:'1px', textTransform:'uppercase' }}>Multimarket Intelligence v4.5</p>
        </div>
        {saved && <div style={{ background: 'rgba(0,200,150,0.15)', border: '1px solid #00C896', borderRadius:'8px', padding: '8px 16px', color: '#00C896', fontSize: '13px' }}>✓ Guardado</div>}
      </div>

      <div style={{ display: 'flex', gap: '4px', marginBottom: '24px', background: 'rgba(255,255,255,0.03)', padding: '4px', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.06)' }}>
        {TABS.map(tab => (
          <button key={tab.key} onClick={() => !isSweeping && setActiveTab(tab.key)} style={{
            flex: 1, padding: '10px 16px', borderRadius: '7px', border: 'none',
            background: activeTab === tab.key ? 'rgba(255,255,255,0.08)' : 'transparent',
            color: activeTab === tab.key ? '#FFF' : '#555',
            cursor: isSweeping ? 'not-allowed' : 'pointer', fontSize: '13px', fontWeight: activeTab === tab.key ? 600 : 400,
            transition: 'all 0.2s',
          }}>
            {tab.label}
            <div style={{ fontSize: '10px', color: activeTab === tab.key ? '#666' : '#444', marginTop: '2px' }}>{tab.subtitle}</div>
          </button>
        ))}
      </div>

      {activeTab === 'crypto' && config && <CryptoSettings config={config} onSave={(data: any) => handleSave('crypto', data)} />}
      {activeTab === 'forex' && config && <ForexSettings config={config} onSave={(data: any) => handleSave('forex', data)} />}
      {activeTab === 'stocks' && uSettings && stocksConfig && (
        <StocksSettings 
            settings={uSettings} 
            stocksConfig={stocksConfig}
            config={config}
            onSave={(data: any) => handleSave('stocks', data, false)} 
            onSaveAndSweep={(data: any) => handleSave('stocks', data, true)}
            onSaveGeneral={(data: any) => handleSave('stocks_general', data)}
            onSaveGlobal={(data: any) => handleSave('system', data)}
        />
      )}
      {activeTab === 'system' && config && <SystemSettings config={config} onSave={(data: any) => handleSave('system', data)} onOpenRules={() => setIsRuleModalOpen(true)} />}

      <RuleEngineModal isOpen={isRuleModalOpen} onClose={() => setIsRuleModalOpen(false)} />
    </div>
  )
}

/* ════════════════════════════════════════════════
   COMPONENTE StocksSettings 
   ════════════════════════════════════════════════ */


const StocksSettings = ({ settings, stocksConfig, config, onSave, onSaveAndSweep, onSaveGeneral, onSaveGlobal }: any) => {
  const [form, setForm] = useState<any>({})
  const [generalForm, setGeneralForm] = useState<any>({})
  const [showUniverse, setShowUniverse] = useState(false)

  useEffect(() => { if (settings) setForm({ ...settings }) }, [settings])
  useEffect(() => { 
    if (stocksConfig && config) {
      setGeneralForm({ 
        ...stocksConfig,
        capital_stocks_spot: config.capital_stocks_spot,
        accumulated_profit_stocks: config.accumulated_profit_stocks,
        leverage_stocks: config.leverage_stocks
      }) 
    } 
  }, [stocksConfig, config])

  if (!form.fg_mcap_min && form.fg_mcap_min !== 0) return <div style={{ padding: '20px', color: '#555' }}>Initializing engine...</div>

  const totalWeight = Number(form.w_rev_growth) + Number(form.w_gross_margin) + Number(form.w_eps_growth) + Number(form.w_rs_score) + Number(form.w_inst_ownership);
  const isValidWeights = Math.abs(totalWeight - 100) < 0.01;

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
      <StatusBadge label="Stocks Industrial" status="ACTIVO" color="#22C55E" detail="Estrategia Fibonacci + AI" />

      {/* SECCIÓN GENERAL SIEMPRE VISIBLE */}
      <SettingsSection title="💰 Configuración de Cuenta & Riesgo">
          <SettingRow label="Capital asignado (Base)" value={generalForm.capital_stocks_spot ?? 0} type="number" prefix="$" onChange={(v: any) => setGeneralForm({ ...generalForm, capital_stocks_spot: v })} />
          <SettingRow label="Ganancia o Profit de la cuenta" value={generalForm.accumulated_profit_stocks ?? 0} type="number" prefix="$" onChange={(v: any) => setGeneralForm({ ...generalForm, accumulated_profit_stocks: v })} />
          <div style={{ padding: '4px 20px', color: '#666', fontSize: '11px', fontStyle: 'italic' }}>
             Capital Operativo Total: ${( Number(generalForm.capital_stocks_spot || 0) + Number(generalForm.accumulated_profit_stocks || 0) ).toLocaleString()} USD
          </div>
          <SettingRow label="Max. Tot Riesgo Inv." value={generalForm.max_total_risk_pct || 30} type="number" suffix="%" onChange={(v: any) => setGeneralForm({ ...generalForm, max_total_risk_pct: v })} />
          <div style={{ padding: '4px 20px', color: '#666', fontSize: '11px', fontStyle: 'italic' }}>
             Límite de exposición: ${( ( Number(generalForm.capital_stocks_spot || 0) + Number(generalForm.accumulated_profit_stocks || 0) ) * ((generalForm.max_total_risk_pct || 30) / 100)).toLocaleString()} USD
          </div>
         <SettingRow label="Apalancamiento (Leverage)" value={generalForm.leverage_stocks ?? 1} type="number" suffix="x" onChange={(v: any) => setGeneralForm({ ...generalForm, leverage_stocks: v })} />
         <SettingRow label="% Inversión por Operación" value={generalForm.max_pct_per_trade} type="number" suffix="%" onChange={(v: any) => setGeneralForm({ ...generalForm, max_pct_per_trade: v })} />
         <SettingToggle label="Paper Trading Active" value={generalForm.paper_mode_active === true || generalForm.paper_mode_active === 'true'} onChange={(v: any) => setGeneralForm({ ...generalForm, paper_mode_active: v })} />
      </SettingsSection>

      <SettingsSection title="🛡️ Stop Loss Adaptativo">
        <div style={{ padding: '0 20px 10px 20px', color: '#666', fontSize: '11px', fontStyle: 'italic' }}>
           Protección inteligente: Si el precio toca el SLV, entra en Modo Recuperación por 2h.
        </div>
        <SettingRow label="Stop Loss absoluto (Hard Stop)" value={generalForm.sl_max_loss_hard} type="number" suffix="%" onChange={(v: any) => setGeneralForm({ ...generalForm, sl_max_loss_hard: v })} />
        <SettingRow label="Pérdida para Modo Recuperación" value={generalForm.sl_close_threshold} type="number" suffix="%" onChange={(v: any) => setGeneralForm({ ...generalForm, sl_close_threshold: v })} />
        <SettingRow label="Pérdida máx. antes de pánico" value={generalForm.sl_wait_threshold} type="number" suffix="%" onChange={(v: any) => setGeneralForm({ ...generalForm, sl_wait_threshold: v })} />
        <SettingRow label="Días máx. en espera" value={generalForm.sl_max_wait_days} type="number" onChange={(v: any) => setGeneralForm({ ...generalForm, sl_max_wait_days: v })} />
        <SettingToggle label="Detectar clímax de volumen" value={generalForm.sl_volume_climax_enabled === true || generalForm.sl_volume_climax_enabled === 'true'} onChange={(v: any) => setGeneralForm({ ...generalForm, sl_volume_climax_enabled: v })} />
      </SettingsSection>

      {/* UNIVERSE BUILDER COMO BOTÓN DESPLEGABLE */}
      <div style={{ 
          background: 'rgba(79,195,247,0.05)', 
          padding: '14px 18px', 
          borderRadius: '10px', 
          border: '1px solid rgba(79,195,247,0.2)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
      }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#4FC3F7', boxShadow: '0 0 8px #4FC3F7' }} />
              <div>
                  <span style={{ color: '#FFF', fontWeight:700, fontSize: '14px' }}>Universe Builder</span>
                  <div style={{ color: '#555', fontSize: '11px' }}>Filtros de selección fundamental</div>
              </div>
          </div>
          <button 
            onClick={() => setShowUniverse(!showUniverse)}
            style={{ 
                background: showUniverse ? '#4FC3F7' : 'transparent', 
                color: showUniverse ? '#000' : '#4FC3F7', 
                border: '1px solid #4FC3F7', 
                padding: '6px 16px', 
                borderRadius: '8px', 
                fontSize: '10px', 
                fontWeight: 900,
                cursor: 'pointer',
                transition: 'all 0.2s'
            }}
          >
            {showUniverse ? 'CERRAR CONFIGURACIÓN' : 'CONFIGURACIÓN'}
          </button>
      </div>

      {showUniverse && (
        <div style={{ display:'flex', flexDirection:'column', gap:'16px', animation: 'fadeIn 0.3s ease' }}>
          {/* Se han movido las secciones de SL fuera de aquí para mayor visibilidad */}
          
          <SettingsSection title="💎 Filtro FUTURE GIANT">
            <SettingRow label="Market Cap mínimo" value={form.fg_mcap_min} type="number" suffix="M" onChange={(v: any) => setForm({ ...form, fg_mcap_min: v })} />
            <SettingRow label="Market Cap máximo" value={form.fg_mcap_max} type="number" suffix="M" onChange={(v: any) => setForm({ ...form, fg_mcap_max: v })} />
            <SettingRow label="Revenue Growth YoY mín." value={form.fg_rev_growth_min} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, fg_rev_growth_min: v })} />
            <SettingRow label="Precio máximo acción" value={form.fg_price_max} type="number" prefix="$" onChange={(v: any) => setForm({ ...form, fg_price_max: v })} />
            <SettingRow label="RS Score mínimo" value={form.fg_rs_min} type="number" onChange={(v: any) => setForm({ ...form, fg_rs_min: v })} />
          </SettingsSection>
          <SettingsSection title="🏆 Filtro GROWTH LEADER">
            <SettingRow label="Market Cap mínimo" value={form.gl_mcap_min} type="number" suffix="M" onChange={(v: any) => setForm({ ...form, gl_mcap_min: v })} />
            <SettingRow label="Revenue Growth YoY mín." value={form.gl_rev_growth_min} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, gl_rev_growth_min: v })} />
            <SettingRow label="Gross Margin mínimo" value={form.gl_margin_min} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, gl_margin_min: v })} />
            <SettingRow label="RS Score mínimo" value={form.gl_rs_min} type="number" onChange={(v: any) => setForm({ ...form, gl_rs_min: v })} />
            <SettingRow label="Inst. Ownership mínimo" value={form.gl_inst_min} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, gl_inst_min: v })} />
            <SettingRow label="Precio máximo acción" value={form.gl_price_max} type="number" prefix="$" onChange={(v: any) => setForm({ ...form, gl_price_max: v })} />
          </SettingsSection>
          <SettingsSection title="⚖️ SCORING (Ponderación)">
            <SettingRow label="Peso Revenue Growth" value={form.w_rev_growth} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, w_rev_growth: v })} />
            <SettingRow label="Peso Gross Margin" value={form.w_gross_margin} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, w_gross_margin: v })} />
            <SettingRow label="Peso EPS Growth" value={form.w_eps_growth} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, w_eps_growth: v })} />
            <SettingRow label="Peso RS Score" value={form.w_rs_score} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, w_rs_score: v })} />
            <SettingRow label="Peso Inst. Ownership" value={form.w_inst_ownership} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, w_inst_ownership: v })} />
            <div style={{ padding: '8px 18px', display: 'flex', justifyContent: 'space-between', borderTop: '1px solid rgba(255,255,255,0.04)', marginTop: '8px' }}>
              <span style={{ fontSize: '11px', color: '#444', fontWeight: 900 }}>SUMA TOTAL:</span>
              <span style={{ fontSize: '13px', fontWeight: 900, color: isValidWeights ? '#00C896' : '#EF4444' }}>{totalWeight}% {isValidWeights ? '✓' : '✗'}</span>
            </div>
          </SettingsSection>
          <div style={{ display:'flex', gap:'12px', padding:'8px 18px' }}>
            <button onClick={() => onSave(form)} disabled={!isValidWeights} style={{ flex:1, padding:'14px', borderRadius:'10px', background:'rgba(255,255,255,0.05)', border:'1px solid rgba(255,255,255,0.1)', color:'#FFF', fontWeight:700, cursor:'pointer' }}>Solo Guardar Filtros</button>
            <button onClick={() => onSaveAndSweep(form)} disabled={!isValidWeights} style={{ flex:1, padding:'14px', borderRadius:'10px', background:'linear-gradient(135deg, #00C896, #00A878)', border:'none', color:'#000', fontWeight:700, cursor:'pointer' }}>💾 Guardar y Re-escanear</button>
          </div>
        </div>
      )}

      <SaveButton onSave={() => {
          const { capital_stocks_spot, accumulated_profit_stocks, leverage_stocks, ...rest } = generalForm;
          
          // 1. Guardar cambios en trading_config (Capital y Leverage)
          const globalUpdate: any = {};
          if (capital_stocks_spot !== undefined) globalUpdate.capital_stocks_spot = capital_stocks_spot;
          if (accumulated_profit_stocks !== undefined) globalUpdate.accumulated_profit_stocks = accumulated_profit_stocks;
          if (leverage_stocks !== undefined) globalUpdate.leverage_stocks = leverage_stocks;
          
          if (Object.keys(globalUpdate).length > 0) {
              onSaveGlobal(globalUpdate);
          }
          
          // 2. Guardar todos los campos de stocks_config (incluyendo Max Tot Riesgo)
          onSaveGeneral(rest);
      }} />

    </div>
  )
}

/* ════════════════════════════════════════════════
   COMPONENTES Crypto, Forex, System 
   ════════════════════════════════════════════════ */
const CryptoSettings = ({ config, onSave }: any) => {
  const [form, setForm] = useState({ 
    capital_crypto_futures: config.capital_crypto_futures || 500, 
    accumulated_profit_crypto: config.accumulated_profit_crypto || 0,
    leverage_crypto: config.leverage_crypto || 15, 
    max_risk_per_trade_pct: config.max_risk_per_trade_pct || 2.0, 
    max_open_trades: config.max_open_trades || 3,
    max_positions_per_symbol: config.max_positions_per_symbol || 3,
    max_total_risk_crypto_pct: config.regime_params?.max_total_risk_crypto_pct || 30,
    active_symbols_str: (config.active_symbols || ["BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT"]).join(', ')
  })

  useEffect(() => {
    setForm({
      ...form,
      active_symbols_str: (config.active_symbols || []).join(', '),
      max_positions_per_symbol: config.max_positions_per_symbol,
      max_risk_per_trade_pct: config.max_risk_per_trade_pct,
      max_total_risk_crypto_pct: config.regime_params?.max_total_risk_crypto_pct || 30
    })
  }, [config.active_symbols, config.max_positions_per_symbol, config.max_risk_per_trade_pct, config.regime_params?.max_total_risk_crypto_pct])

  const handleLocalSave = () => {
    const symbols = form.active_symbols_str.split(',').map(s => s.trim().toUpperCase()).filter(s => s !== '')
    const newRegimeParams = { ...config.regime_params, max_total_risk_crypto_pct: form.max_total_risk_crypto_pct }
    onSave({
      ...form,
      active_symbols: symbols,
      regime_params: newRegimeParams
    })
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
      <StatusBadge label="Binance Futures" status="ACTIVO" color="#F7931A" detail="Paper Trading" />
      <SettingsSection title="💰 Capital & Activos">
        <SettingRow label="Capital asignado (Base)" value={form.capital_crypto_futures} type="number" prefix="$" onChange={(v: any) => setForm({ ...form, capital_crypto_futures: v })} />
        <SettingRow label="Ganancia o Profit de la cuenta" value={form.accumulated_profit_crypto} type="number" prefix="$" onChange={(v: any) => setForm({ ...form, accumulated_profit_crypto: v })} />
        <div style={{ padding: '4px 20px', color: 'var(--text-muted)', fontSize: '11px', fontStyle: 'italic' }}>
             Capital Operativo Total: ${( Number(form.capital_crypto_futures) + Number(form.accumulated_profit_crypto) ).toLocaleString()} USD
        </div>
        <SettingRow label="Apalancamiento (Leverage)" value={form.leverage_crypto} type="number" suffix="x" onChange={(v: any) => setForm({ ...form, leverage_crypto: v })} />
        <SettingRow label="% Inversión (Global Portion)" value={config.pct_for_trading || 20} type="number" suffix="%" onChange={(v: any) => onSave({ pct_for_trading: v })} />
      <SettingRow label="Criptos Operan" value={form.active_symbols_str} flexInput onChange={(v: any) => setForm({ ...form, active_symbols_str: v })} />
        <div style={{ padding: '4px 18px', color: '#555', fontSize: '10px' }}>Total Criptos: {(form.active_symbols_str.split(',').filter(s => s.trim() !== '').length)}</div>
      </SettingsSection>
      
      <SettingsSection title="🛡️ Gestión de Riesgo (Cripto)">
        <SettingRow label="Max. Tot Riesgo Inv." value={form.max_total_risk_crypto_pct} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, max_total_risk_crypto_pct: v })} />
        <SettingRow label="Cant. Operación x Cripto" value={form.max_positions_per_symbol} type="number" onChange={(v: any) => setForm({ ...form, max_positions_per_symbol: v })} />
        <SettingRow label="Inversión x Operación (Risk %)" value={form.max_risk_per_trade_pct} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, max_risk_per_trade_pct: v })} />
        <div style={{ padding: '8px 18px', color: 'var(--text-muted)', fontSize: '11px' }}>
          Equivale a approx. ${(form.capital_crypto_futures * (form.max_risk_per_trade_pct / 100)).toFixed(2)} USD por cada compra/venta.
        </div>
      </SettingsSection>

      <SaveButton onSave={handleLocalSave} />
    </div>
  )
}

const ForexSettings = ({ config, onSave }: any) => {
  const isConnected = config.capital_forex_futures > 0
  const [form, setForm] = useState({ 
    max_positions_per_symbol: config.max_positions_per_symbol || 3,
    max_risk_per_trade_pct: config.max_risk_per_trade_pct || 2.0,
    max_total_risk_forex_pct: config.regime_params?.max_total_risk_forex_pct || 30,
    forex_symbols_str: (config.regime_params?.forex_assets || ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD"]).join(', ')
  })

  useEffect(() => {
    setForm({
      max_positions_per_symbol: config.max_positions_per_symbol,
      max_risk_per_trade_pct: config.max_risk_per_trade_pct,
      max_total_risk_forex_pct: config.regime_params?.max_total_risk_forex_pct || 30,
      forex_symbols_str: (config.regime_params?.forex_assets || []).join(', ')
    })
  }, [config.max_positions_per_symbol, config.max_risk_per_trade_pct, config.regime_params?.forex_assets, config.regime_params?.max_total_risk_forex_pct])

  const handleLocalSave = () => {
    const symbols = form.forex_symbols_str.split(',').map(s => s.trim().toUpperCase()).filter(s => s !== '')
    const newRegimeParams = { ...config.regime_params, forex_assets: symbols, max_total_risk_forex_pct: form.max_total_risk_forex_pct }
    onSave({
      ...form,
      regime_params: newRegimeParams
    })
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
      <StatusBadge label="IC Markets / cTrader" status={isConnected ? 'ACTIVO' : 'PENDIENTE'} color={isConnected ? '#00C896' : '#555'} detail="Conexión API" />
      <SettingsSection title="💰 Gestión Forex">
        <SettingRow label="Capital asignado (Base)" value={config.capital_forex_futures} type="number" prefix="$" disabled={!isConnected} onChange={(v: any) => onSave({ capital_forex_futures: v })} />
        <SettingRow label="Ganancia o Profit de la cuenta" value={config.accumulated_profit_forex || 0} type="number" prefix="$" onChange={(v: any) => onSave({ accumulated_profit_forex: v })} />
        <div style={{ padding: '4px 20px', color: 'var(--text-muted)', fontSize: '11px', fontStyle: 'italic' }}>
             Capital Operativo Total: ${( Number(config.capital_forex_futures) + Number(config.accumulated_profit_forex || 0) ).toLocaleString()} USD
        </div>
        <SettingRow label="Apalancamiento (Leverage)" value={config.leverage_forex || 500} type="number" suffix="x" onChange={(v: any) => onSave({ leverage_forex: v })} />
        <SettingRow label="% Inversión (Global Portion)" value={config.pct_for_trading || 20} type="number" suffix="%" onChange={(v: any) => onSave({ pct_for_trading: v })} />
        <SettingRow label="Monedas Operan" value={form.forex_symbols_str} flexInput onChange={(v: any) => setForm({ ...form, forex_symbols_str: v })} />
      </SettingsSection>

      <SettingsSection title="🛡️ Gestión de Riesgo (Forex)">
        <SettingRow label="Max. Tot Riesgo Inv." value={form.max_total_risk_forex_pct} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, max_total_risk_forex_pct: v })} />
        <SettingRow label="Cant. Operación x Par" value={form.max_positions_per_symbol} type="number" onChange={(v: any) => setForm({ ...form, max_positions_per_symbol: v })} />
        <SettingRow label="Inversión x Operación (Risk %)" value={form.max_risk_per_trade_pct} type="number" suffix="%" onChange={(v: any) => setForm({ ...form, max_risk_per_trade_pct: v })} />
      </SettingsSection>

      <SaveButton onSave={handleLocalSave} />
    </div>
  )
}

const SystemSettings = ({ config, onSave, onOpenRules }: any) => {
  const [form, setForm] = useState({ telegram_enabled: config.telegram_enabled ?? true, ai_enabled: config.ai_enabled ?? true, paper_trading: config.paper_trading ?? true })
  const [theme, setTheme] = useState<any>({
    bgColor: '#0a0e17',
    bgImage: '',
    titleFont: 'Inter',
    headerFont: 'Inter',
    contentFont: 'Inter',
    contentColor: '#e2e8f0'
  })

  useEffect(() => {
    const saved = localStorage.getItem('app_theme_custom')
    if (saved) setTheme(JSON.parse(saved))
  }, [])

  const saveTheme = () => {
    localStorage.setItem('app_theme_custom', JSON.stringify(theme))
    window.dispatchEvent(new Event('themeUpdated'))
    alert("🎨 Apariencia actualizada correctamente.")
  }

  const resetTheme = () => {
    localStorage.removeItem('app_theme_custom')
    window.dispatchEvent(new Event('themeUpdated'))
    setTheme({
        bgColor: '#0a0e17',
        bgImage: '',
        titleFont: 'Inter',
        headerFont: 'Inter',
        contentFont: 'Inter',
        contentColor: '#e2e8f0'
    })
    alert("♻️ Estilos restablecidos a valores de fábrica.")
  }

  const fontOptions = ['Inter', 'Roboto', 'Montserrat', 'Oswald', 'Outfit', 'JetBrains Mono', 'Poppins', 'Lato', 'Playfair Display']

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:'16px' }}>
      <SettingsSection title="📱 Alertas">
        <SettingToggle label="Telegram Activado" value={form.telegram_enabled} onChange={(v: any) => setForm({ ...form, telegram_enabled: v })} />
      </SettingsSection>
      
      <SettingsSection title="🧠 Algoritmo Core">
        <div style={{ padding: '12px 18px' }}>
            <button onClick={onOpenRules} style={{ width: '100%', padding: '10px', background: 'rgba(79,195,247,0.1)', border: '1px solid rgba(79,195,247,0.3)', borderRadius: '8px', color: '#4FC3F7', fontSize: '11px', fontWeight: 700, cursor: 'pointer' }}>⚙️ EDITAR REGLAS (RULE ENGINE)</button>
        </div>
      </SettingsSection>

      <SettingsSection title="🎨 Apariencia (Customización UI)">
        <div style={{ padding: '10px 18px', display:'flex', alignItems:'center', gap:'16px' }}>
            <div style={{ flex:1, color:'var(--text-secondary)', fontSize:'13px' }}>Color Fondo (Background)</div>
            <div style={{ display:'flex', gap:'8px' }}>
                <button 
                    onClick={() => setTheme({ ...theme, bgColor: '#0a0e17', contentColor: '#e2e8f0' })}
                    style={{ padding:'6px 12px', borderRadius:'6px', background:'#0a0e17', color:'#FFF', border:'1px solid #333', fontSize:'10px', fontWeight:900, cursor:'pointer' }}
                >DARK</button>
                <button 
                    onClick={() => setTheme({ ...theme, bgColor: '#ffffff', contentColor: '#1e293b' })}
                    style={{ padding:'6px 12px', borderRadius:'6px', background:'#FFF', color:'#000', border:'1px solid #CCC', fontSize:'10px', fontWeight:900, cursor:'pointer' }}
                >LIGHT</button>
                <input type="color" value={theme.bgColor} onChange={(e) => setTheme({ ...theme, bgColor: e.target.value })} style={{ width:'30px', height:'30px', border:'none', background:'none', cursor:'pointer' }} />
            </div>
        </div>
        <SettingRow label="Imagen Fondo (URL)" value={theme.bgImage} flexInput onChange={(v: any) => setTheme({ ...theme, bgImage: v })} />
        
        <div style={{ padding: '10px 18px', display:'flex', alignItems:'center', gap:'16px' }}>
            <div style={{ flex:1, color:'var(--text-secondary)', fontSize:'13px' }}>Tipografía Títulos</div>
            <select value={theme.titleFont} onChange={(e) => setTheme({ ...theme, titleFont: e.target.value })} style={SelectStyle}>
                {fontOptions.map(f => <option key={f} value={f} style={{ color: '#000' }}>{f}</option>)}
            </select>
        </div>

        <div style={{ padding: '10px 18px', display:'flex', alignItems:'center', gap:'16px' }}>
            <div style={{ flex:1, color:'var(--text-secondary)', fontSize:'13px' }}>Tipografía Columnas (Tablas)</div>
            <select value={theme.headerFont} onChange={(e) => setTheme({ ...theme, headerFont: e.target.value })} style={SelectStyle}>
                {fontOptions.map(f => <option key={f} value={f} style={{ color: '#000' }}>{f}</option>)}
            </select>
        </div>

        <div style={{ padding: '10px 18px', display:'flex', alignItems:'center', gap:'16px' }}>
            <div style={{ flex:1, color:'var(--text-secondary)', fontSize:'13px' }}>Tipografía Contenido</div>
            <select value={theme.contentFont} onChange={(e) => setTheme({ ...theme, contentFont: e.target.value })} style={SelectStyle}>
                {fontOptions.map(f => <option key={f} value={f} style={{ color: '#000' }}>{f}</option>)}
            </select>
        </div>

        <SettingRow label="Color de Texto Contenido" value={theme.contentColor} type="color" onChange={(v: any) => setTheme({ ...theme, contentColor: v })} />
        
        <div style={{ padding:'12px 18px', display:'flex', gap:'12px' }}>
            <button onClick={resetTheme} style={{ flex:1, padding:'10px', background:'rgba(255,255,255,0.05)', border:'1px solid var(--border-color)', color:'var(--text-primary)', fontSize:'11px', fontWeight:700, borderRadius:'8px', cursor:'pointer' }}>RESTABLECER</button>
            <button onClick={saveTheme} style={{ flex:1, padding:'10px', background:'rgba(79,195,247,0.1)', border:'1px solid rgba(79,195,247,0.3)', borderRadius:'8px', color:'#4FC3F7', fontSize:'11px', fontWeight:700, cursor:'pointer' }}>APLICAR ESTILOS</button>
        </div>
      </SettingsSection>

      <SaveButton onSave={() => onSave(form)} />
    </div>
  )
}

/* ════════════════════════════════════════════════
   HELPERS 
   ════════════════════════════════════════════════ */
const StatusBadge = ({ label, status, color, detail }: any) => (
  <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '14px 18px', background: `rgba(${color === '#F7931A' ? '247,147,26' : '79,195,247'}, 0.05)`, borderRadius: '10px', border: `1px solid ${color}22` }}>
    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, boxShadow: `0 0 8px ${color}` }} />
    <div style={{ flex:1 }}><span style={{ color: '#FFF', fontWeight:700, fontSize: '14px' }}>{label}</span><div style={{ color: '#555', fontSize: '11px' }}>{detail}</div></div>
    <div style={{ padding: '4px 12px', borderRadius: '20px', background: `${color}22`, border: `1px solid ${color}44`, color: color, fontSize: '10px', fontWeight: 900, letterSpacing:'1px' }}>{status}</div>
  </div>
)
const SettingsSection = ({ title, children }: any) => (
  <div style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-color)', borderRadius: '10px', overflow: 'hidden' }}><div style={{ padding: '12px 18px', borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)', fontSize: '10px', fontWeight: 900, textTransform: 'uppercase' }}>{title}</div>{children}</div>)
const SettingRow = ({ label, value, type, prefix, suffix, onChange, disabled, flexInput }: any) => (
  <div style={{ display: 'flex', alignItems: 'center', padding: '10px 18px', gap: '16px', opacity: disabled ? 0.3 : 1 }}>
    <div style={{ flex: flexInput ? '0 0 150px' : 1, color: 'var(--text-secondary)', fontSize: '13px' }}>{label}</div>
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flex: flexInput ? 1 : 'none' }}>
      {prefix && <span style={{ color:'var(--text-muted)', fontSize:'13px' }}>{prefix}</span>}
      <input 
        type={type || 'text'} 
        value={value} 
        disabled={disabled} 
        onChange={e => onChange(type === 'number' ? parseFloat(e.target.value) : e.target.value)} 
        style={{ 
          width: flexInput ? '100%' : '100px', 
          padding: '6px 10px', 
          background: 'rgba(255,255,255,0.05)', 
          border: '1px solid var(--border-color)', 
          borderRadius: '6px', 
          color: 'var(--text-primary)', 
          fontSize: '13px', 
          textAlign: flexInput ? 'left' : 'right', 
          outline:'none' 
        }} 
      />
      {suffix && <span style={{ color:'var(--text-muted)', fontSize:'13px' }}>{suffix}</span>}
    </div>
  </div>
)
const SettingToggle = ({ label, value, onChange }: any) => (
  <div style={{ display: 'flex', alignItems: 'center', padding: '10px 18px', gap: '16px' }}><div style={{ flex:1, color:'var(--text-secondary)', fontSize:'13px' }}>{label}</div>
    <div onClick={() => onChange(!value)} style={{ width: '40px', height: '20px', borderRadius: '10px', background: value ? '#00C896' : '#222', position: 'relative', cursor: 'pointer' }}><div style={{ position: 'absolute', top: '2px', left: value ? '22px' : '2px', width: '16px', height: '16px', borderRadius:'50%', background: '#FFF' }} /></div>
  </div>
)
const SaveButton = ({ onSave }: any) => (<div style={{ padding: '8px 18px' }}><button onClick={onSave} style={{ width: '100%', padding: '14px', borderRadius: '10px', background: 'linear-gradient(135deg, #00C896, #00A878)', color: '#000', fontSize: '13px', fontWeight: 700, cursor: 'pointer', border:'none' }}>💾 Guardar Cambios</button></div>)

const SelectStyle = {
    padding: '6px 10px',
    background: 'rgba(255,255,255,0.05)',
    border: '1px solid var(--border-color)',
    borderRadius: '6px',
    color: 'var(--text-primary)',
    fontSize: '13px',
    outline: 'none',
    cursor: 'pointer'
}
