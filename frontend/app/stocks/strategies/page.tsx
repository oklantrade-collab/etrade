"use client"
import { useState, useEffect } from 'react'

const GROUP_CONFIG: Record<string, any> = {
  inversiones_pro: {
    label: '🏦 Inversiones PRO',
    color: '#4FC3F7',
    bg:    'rgba(79,195,247,0.08)',
  },
  hot_by_volume: {
    label: '🔥 Hot by Volume',
    color: '#FF8A65',
    bg:    'rgba(255,138,101,0.08)',
  },
}

const ORDER_TYPE_CONFIG: Record<string, any> = {
  market: { label: 'MARKET', color: '#00C896', icon: '⚡' },
  limit:  { label: 'LIMIT',  color: '#FFB74D', icon: '📍' },
}

export default function StocksStrategies() {
  const [rules, setRules] = useState<any[]>([])
  const [activeGroup, setActiveGroup] = useState('inversiones_pro')
  const [activeDir, setActiveDir] = useState('buy')
  const [editRule, setEditRule] = useState<any | null>(null)

  useEffect(() => {
    loadRules()
  }, [])

  const loadRules = () => {
    fetch('/api/v1/stocks/rules')
      .then(r => r.json())
      .then(data => {
          if(Array.isArray(data)) setRules(data)
      })
  }

  const filteredRules = rules.filter(r =>
    (!activeGroup || r.group_name === activeGroup) &&
    (!activeDir   || r.direction  === activeDir)
  )

  return (
    <div style={{ padding:'24px', background: '#0B0E14', minHeight: '100vh', color: '#FFF' }}>
      {/* HEADER */}
      <div style={{
        display:      'flex',
        alignItems:   'center',
        marginBottom: '24px',
        gap:          '12px',
      }}>
        <h1 style={{
          fontSize:'20px', fontWeight:700,
          color:'#FFF', margin:0
        }}>
          📈 Stocks — Strategy Engine
        </h1>
        <span style={{
          background: 'rgba(0,200,150,0.15)',
          border:     '1px solid #00C89633',
          borderRadius:'6px',
          padding:    '3px 10px',
          color:      '#00C896',
          fontSize:   '12px',
        }}>
          {rules.filter(r => r.enabled).length} reglas activas
        </span>
      </div>

      {/* TABS DE GRUPOS */}
      <div style={{
        display:      'flex',
        gap:          '8px',
        marginBottom: '16px',
      }}>
        {Object.entries(GROUP_CONFIG).map(
          ([key, cfg]) => (
            <button
              key={key}
              onClick={() => setActiveGroup(key)}
              style={{
                padding:    '10px 20px',
                borderRadius:'8px',
                border:     `1px solid ${
                  activeGroup === key
                    ? cfg.color
                    : 'rgba(255,255,255,0.08)'
                }`,
                background: activeGroup === key
                  ? cfg.bg : 'transparent',
                color:      activeGroup === key
                  ? cfg.color : '#666',
                fontWeight: activeGroup === key
                  ? 700 : 400,
                cursor:     'pointer',
                fontSize:   '13px',
              }}>
              {cfg.label}
            </button>
          )
        )}
      </div>

      {/* TABS BUY / SELL */}
      <div style={{
        display:      'flex',
        gap:          '4px',
        marginBottom: '20px',
      }}>
        {['buy','sell'].map(dir => (
          <button
            key={dir}
            onClick={() => setActiveDir(dir)}
            style={{
              padding:    '6px 20px',
              borderRadius:'20px',
              border:     `1px solid ${
                activeDir === dir
                  ? (dir === 'buy'
                     ? '#00C896' : '#FF4757')
                  : 'rgba(255,255,255,0.08)'
              }`,
              background: activeDir === dir
                ? (dir === 'buy'
                   ? 'rgba(0,200,150,0.12)'
                   : 'rgba(255,71,87,0.12)')
                : 'transparent',
              color:      activeDir === dir
                ? (dir === 'buy'
                   ? '#00C896' : '#FF4757')
                : '#666',
              cursor:     'pointer',
              fontWeight: 600,
              fontSize:   '12px',
            }}>
            {dir === 'buy' ? '🟢 BUY' : '🔴 SELL'}
          </button>
        ))}
      </div>

      {/* RULE CARDS */}
      <div style={{
        display:'flex', flexDirection:'column',
        gap:'12px'
      }}>
        {filteredRules.map(rule => (
          <StocksRuleCard
            key={rule.rule_code}
            rule={rule}
            groupConfig={GROUP_CONFIG[rule.group_name]}
            onEdit={() => setEditRule(rule)}
          />
        ))}
      </div>

      {/* MODAL DE EDICIÓN */}
      {editRule && (
        <EditRuleModal 
          rule={editRule} 
          onSave={() => { setEditRule(null); loadRules(); }} 
          onClose={() => setEditRule(null)} 
        />
      )}
    </div>
  )
}

const StocksRuleCard = ({
  rule, groupConfig, onEdit
}: { rule: any, groupConfig: any, onEdit: any }) => {
  const [expanded, setExpanded] = useState(false)
  const otCfg = ORDER_TYPE_CONFIG[rule.order_type]

  return (
    <div style={{
      background:   'rgba(255,255,255,0.02)',
      border:       `1px solid ${
        rule.enabled
          ? 'rgba(255,255,255,0.08)'
          : 'rgba(255,255,255,0.03)'
      }`,
      borderLeft:   `3px solid ${
        rule.direction === 'buy'
          ? '#00C896' : '#FF4757'
      }`,
      borderRadius: '8px',
      overflow:     'hidden',
      opacity:      rule.enabled ? 1 : 0.5,
    }}>

      {/* HEADER */}
      <div
        onClick={() => setExpanded(!expanded)}
        style={{
          display:    'flex',
          alignItems: 'center',
          padding:    '12px 16px',
          cursor:     'pointer',
          gap:        '10px',
        }}>

        {/* CÓDIGO Y TIPO */}
        <div style={{display: 'flex', alignItems: 'center'}}>
          <span style={{
            fontFamily: 'monospace',
            fontSize:   '14px',
            fontWeight: 700,
            color:      rule.direction === 'buy'
              ? '#00C896' : '#FF4757',
            minWidth:   '40px'
          }}>
            {rule.rule_code}
          </span>
          <span style={{
            marginLeft:   '8px',
            padding:      '2px 8px',
            borderRadius: '4px',
            background:   `${otCfg.color}22`,
            border:       `1px solid ${otCfg.color}44`,
            color:        otCfg.color,
            fontSize:     '10px',
            fontWeight:   700,
            display: 'flex', alignItems: 'center', gap: '4px'
          }}>
            {otCfg.icon} {otCfg.label}
          </span>
        </div>

        {/* NOMBRE */}
        <span style={{
          flex:1, fontSize:'12px', color:'#CCC', fontWeight: 600, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'
        }}>
          {rule.name}
        </span>

        {/* BADGES */}
        <div style={{
          display:'flex', gap:'6px',
          alignItems:'center'
        }}>
          {rule.ia_min > 0 && (
            <span style={{
              fontSize:'11px', color:'#FFB74D',
              background:'rgba(255,183,77,0.10)',
              padding:'2px 8px', borderRadius:'4px',
            }}>
              IA≥{rule.ia_min}
            </span>
          )}
          {rule.tech_score_min > 0 && (
            <span style={{
              fontSize:'11px', color:'#4FC3F7',
              background:'rgba(79,195,247,0.10)',
              padding:'2px 8px', borderRadius:'4px',
            }}>
              Tech≥{rule.tech_score_min}
            </span>
          )}
          {(rule.fundamental_score_min > 0 || rule.rule_code === 'S01' || rule.rule_code === 'S02' || rule.rule_code === 'S09') && (
            <span style={{
              fontSize:'11px', color:'#22C55E',
              background:'rgba(34,197,94,0.10)',
              padding:'2px 8px', borderRadius:'4px',
            }}>
              Fund≥{rule.fundamental_score_min || (rule.rule_code === 'S01' ? 70 : (rule.rule_code === 'S02' ? 65 : (rule.rule_code === 'S09' ? 70 : 0)))}
            </span>
          )}
          {rule.dca_enabled && (
            <span style={{
              fontSize:'11px', color:'#CE93D8',
              background:'rgba(206,147,216,0.10)',
              padding:'2px 8px', borderRadius:'4px',
            }}>
              DCA×{rule.dca_max_buys}
            </span>
          )}
          {rule.close_all && (
            <span style={{
              fontSize:'11px', color:'#FF4757',
              background:'rgba(255,71,87,0.10)',
              padding:'2px 8px', borderRadius:'4px',
            }}>
              CIERRE TOTAL
            </span>
          )}
        </div>

        {/* BOTÓN EDITAR */}
        <button
          onClick={e => { e.stopPropagation(); onEdit(); }}
          style={{
            padding:    '4px 10px',
            background: 'rgba(255,255,255,0.05)',
            border:     '1px solid #444',
            borderRadius:'4px',
            color:      '#AAA',
            cursor:     'pointer',
            fontSize:   '11px',
            fontWeight: 700
          }}>
          ✏️ EDITAR
        </button>

        <span style={{
          color:'#444', fontSize:'12px',
          transform: expanded ? 'rotate(90deg)' : 'none',
          transition:'transform 0.2s',
          marginLeft: '8px'
        }}>▶</span>
      </div>

      {/* DETALLE EXPANDIBLE */}
      {expanded && (
        <div style={{
          borderTop:  '1px solid rgba(255,255,255,0.04)',
          padding:    '12px 16px',
          fontSize:   '12px',
          color:      '#888',
        }}>
          <div style={{marginBottom:'6px'}}>
            <b style={{color:'#CCC'}}>Movimientos:</b>{' '}
            {(rule.movements_allowed || []).join(', ')}
          </div>
          {rule.pine_signal && (
            <div style={{marginBottom:'6px'}}>
              <b style={{color:'#CCC'}}>Pine Signal:</b>{' '}
              {rule.pine_signal}
              {rule.pine_required ? ' (requerida)' : ' (OR Fibonacci)'}
            </div>
          )}
          {rule.fib_trigger?.length > 0 && (
            <div style={{marginBottom:'6px'}}>
              <b style={{color:'#CCC'}}>Fibonacci trigger:</b>{' '}
              Zona {rule.fib_trigger.join(', ')}
            </div>
          )}
          {rule.rvol_min > 0 && (
            <div style={{marginBottom:'6px'}}>
              <b style={{color:'#CCC'}}>RVOL mínimo:</b>{' '}
              {rule.rvol_min}x
            </div>
          )}
          {rule.order_type === 'limit' && (
            <div style={{marginBottom:'6px'}}>
              <b style={{color:'#FFB74D'}}>
                Trigger LIMIT:
              </b>{' '}
              Precio dentro del{' '}
              {((rule.limit_trigger_pct || 0) * 100).toFixed(1)}%
              del precio estimado
            </div>
          )}
          {rule.notes && (
            <div style={{
              marginTop:'8px', color:'#555',
              fontStyle:'italic', background: 'rgba(255,255,255,0.02)', padding: '8px', borderRadius: '4px'
            }}>
              {rule.rule_code === 'S02' ? 
                "MODELO MATH S02: Compra LIMIT en min(Bollinger Lower 1D, Precio Intrínseco * 0.95). Activación si precio < (BB Lower * 1.02). Expira en 5 días." 
                : rule.notes}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function EditRuleModal({ rule, onSave, onClose }: any) {
  const [form, setForm] = useState({ ...rule })
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch(`/api/v1/stocks/rules/${rule.rule_code}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form)
      })
      if (res.ok) onSave()
      else alert('Error guardando regla')
    } catch (err) {
      console.error(err)
    } finally {
      setSaving(false)
    }
  }

  const MOVEMENTS = [
    'ascending', 'descending', 'lateral_ascending', 'lateral_at_top', 
    'lateral_at_bottom', 'asc_from_low', 'descending_from_top', 'irregular'
  ]

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 10000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
      <div onClick={onClose} style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.85)', backdropFilter: 'blur(4px)' }} />
      <div style={{ position: 'relative', background: '#161922', border: '1px solid #333', borderRadius: '24px', width: '100%', maxWidth: '600px', maxHeight: '90vh', overflowY: 'auto', padding: '30px', boxShadow: '0 20px 50px rgba(0,0,0,0.5)' }}>
        <h2 style={{ fontSize: '20px', fontWeight: 900, marginBottom: '20px', display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ color: rule.direction === 'buy' ? '#00C896' : '#FF4757', fontFamily: 'monospace' }}>{rule.rule_code}</span>
          Configuración de Regla
        </h2>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px', marginBottom: '20px' }}>
          <div style={{ gridColumn: 'span 2' }}>
            <label style={{ fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>Nombre de la Regla</label>
            <input value={form.name} onChange={e => setForm({...form, name: e.target.value})} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '10px', color: '#FFF', marginTop: '5px' }} />
          </div>

          <div>
            <label style={{ fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>IA Score Min</label>
            <input type="number" step="0.5" value={form.ia_min} onChange={e => setForm({...form, ia_min: Number(e.target.value)})} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '10px', color: '#FFB74D', marginTop: '5px' }} />
          </div>
          <div>
            <label style={{ fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>Technical Score Min</label>
            <input type="number" value={form.tech_score_min} onChange={e => setForm({...form, tech_score_min: Number(e.target.value)})} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '10px', color: '#4FC3F7', marginTop: '5px' }} />
          </div>

          <div>
             <label style={{ fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>Fundamental Score Min</label>
             <input type="number" value={form.fundamental_score_min || (form.rule_code === 'S01' ? 70 : (form.rule_code === 'S02' ? 65 : (form.rule_code === 'S09' ? 70 : 0)))} onChange={e => setForm({...form, fundamental_score_min: Number(e.target.value)})} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '10px', color: '#22C55E', marginTop: '5px' }} />
          </div>
          <div>
             <label style={{ fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>Limit Trigger %</label>
             <input type="number" step="0.001" value={form.limit_trigger_pct} onChange={e => setForm({...form, limit_trigger_pct: Number(e.target.value)})} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '10px', color: '#FFF', marginTop: '5px' }} />
          </div>

          <div style={{ gridColumn: 'span 2' }}>
            <label style={{ fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>Movimientos Permitidos</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', marginTop: '8px' }}>
              {MOVEMENTS.map(m => {
                const active = (form.movements_allowed || []).includes(m)
                return (
                  <button key={m} onClick={() => {
                    const current = form.movements_allowed || []
                    const next = active ? current.filter((x: string) => x !== m) : [...current, m]
                    setForm({...form, movements_allowed: next})
                  }} style={{
                    fontSize: '9px', padding: '4px 10px', borderRadius: '15px', border: `1px solid ${active ? '#00C896' : '#333'}`,
                    background: active ? 'rgba(0,200,150,0.1)' : 'transparent', color: active ? '#00C896' : '#666', cursor: 'pointer'
                  }}>{m.replace('_', ' ')}</button>
                )
              })}
            </div>
          </div>

          <div style={{ background: 'rgba(255,255,255,0.02)', padding: '15px', borderRadius: '12px', gridColumn: 'span 2' }}>
             <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                <input type="checkbox" checked={form.dca_enabled} onChange={e => setForm({...form, dca_enabled: e.target.checked})} />
                <label style={{ fontSize: '11px', fontWeight: 800 }}>Habilitar DCA (Dollar Cost Averaging)</label>
             </div>
             {form.dca_enabled && (
               <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                 <div>
                   <label style={{ fontSize: '9px', color: '#555' }}>Máximo de Recompras</label>
                   <input type="number" value={form.dca_max_buys} onChange={e => setForm({...form, dca_max_buys: Number(e.target.value)})} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '8px', color: '#FFF' }} />
                 </div>
                 <div>
                   <label style={{ fontSize: '9px', color: '#555' }}>Drop % Mínimo</label>
                   <input type="number" step="0.5" value={form.dca_min_drop_pct} onChange={e => setForm({...form, dca_min_drop_pct: Number(e.target.value)})} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '8px', color: '#FFF' }} />
                 </div>
               </div>
             )}
          </div>

          <div style={{ gridColumn: 'span 2' }}>
            <label style={{ fontSize: '10px', color: '#666', fontWeight: 800, textTransform: 'uppercase' }}>Notas / Racional</label>
            <textarea value={form.notes} onChange={e => setForm({...form, notes: e.target.value})} style={{ width: '100%', background: '#000', border: '1px solid #333', borderRadius: '8px', padding: '10px', color: '#AAA', marginTop: '5px', fontSize: '12px', minHeight: '60px' }} />
          </div>
        </div>

        <div style={{ display: 'flex', gap: '10px', marginTop: '25px' }}>
          <button onClick={onClose} style={{ flex: 1, padding: '12px', background: 'transparent', border: '1px solid #333', color: '#666', borderRadius: '12px', cursor: 'pointer', fontWeight: 800 }}>DESCARTAR</button>
          <button onClick={handleSave} disabled={saving} style={{ flex: 2, padding: '12px', background: '#00C896', border: 'none', color: '#000', borderRadius: '12px', cursor: 'pointer', fontWeight: 950 }}>
            {saving ? 'GUARDANDO...' : 'APLICAR CONFIGURACIÓN'}
          </button>
        </div>
      </div>
    </div>
  )
}
