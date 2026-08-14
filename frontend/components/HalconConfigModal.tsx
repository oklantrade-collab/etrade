import React, { useState, useEffect } from 'react';

interface ConfigSection {
  title: string;
  keys: { key: string; label: string; type: 'number' | 'text' }[];
}

const CONFIG_SECTIONS: ConfigSection[] = [
  {
    title: 'Scoring Weights',
    keys: [
      { key: 'weight_trend', label: 'Trend Weight', type: 'number' },
      { key: 'weight_momentum', label: 'Momentum Weight', type: 'number' },
      { key: 'weight_volatility', label: 'Volatility Weight', type: 'number' },
      { key: 'weight_volume', label: 'Volume Weight', type: 'number' },
    ]
  },
  {
    title: 'Umbrales de Cierre',
    keys: [
      { key: 'close_threshold_profit', label: 'Profit Threshold', type: 'number' },
      { key: 'close_threshold_loss', label: 'Loss Threshold', type: 'number' },
    ]
  },
  {
    title: 'ADX / Régimen',
    keys: [
      { key: 'adx_threshold_strong', label: 'Strong Trend ADX', type: 'number' },
      { key: 'adx_threshold_weak', label: 'Weak Trend ADX', type: 'number' },
    ]
  },
  {
    title: 'RSI',
    keys: [
      { key: 'rsi_overbought', label: 'Overbought Level', type: 'number' },
      { key: 'rsi_oversold', label: 'Oversold Level', type: 'number' },
    ]
  },
  {
    title: 'Compresión EMA',
    keys: [
      { key: 'ema_compression_threshold', label: 'Compression Threshold (%)', type: 'number' },
    ]
  },
  {
    title: 'Volumen',
    keys: [
      { key: 'volume_multiplier', label: 'Confirmation Multiplier', type: 'number' },
    ]
  },
  {
    title: 'ORÁCULO',
    keys: [
      { key: 'oraculo_pre_event_mins', label: 'Pre-Event Window (mins)', type: 'number' },
      { key: 'oraculo_post_event_mins', label: 'Post-Event Window (mins)', type: 'number' },
      { key: 'oraculo_pnl_protect', label: 'PNL Protect Threshold', type: 'number' },
    ]
  },
  {
    title: 'General',
    keys: [
      { key: 'min_profit_pct', label: 'Min Profit (%)', type: 'number' },
      { key: 'partial_close_pct', label: 'Partial Close (%)', type: 'number' },
    ]
  }
];

interface HalconConfigModalProps {
  onClose: () => void;
}

export default function HalconConfigModal({ onClose }: HalconConfigModalProps) {
  const [config, setConfig] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Trigger animation
    setTimeout(() => setIsVisible(true), 10);
    
    // Fetch current config
    // fetch('http://localhost:8080/api/v1/halcon/config')
    
    // Mock data
    setConfig({
      weight_trend: 40,
      weight_momentum: 30,
      weight_volatility: 20,
      weight_volume: 10,
      close_threshold_profit: 75,
      close_threshold_loss: -50,
      adx_threshold_strong: 25,
      adx_threshold_weak: 15,
      rsi_overbought: 70,
      rsi_oversold: 30,
      ema_compression_threshold: 0.15,
      volume_multiplier: 1.5,
      oraculo_pre_event_mins: 60,
      oraculo_post_event_mins: 30,
      oraculo_pnl_protect: 2.0,
      min_profit_pct: 0.5,
      partial_close_pct: 50,
    });
    setLoading(false);
  }, []);

  const handleChange = (key: string, value: string) => {
    setConfig({ ...config, [key]: Number(value) });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await fetch('http://localhost:8080/api/v1/halcon/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config)
      });
      // Handle success
      setTimeout(() => {
        setSaving(false);
        handleClose();
      }, 500);
    } catch (e) {
      console.error('Failed to save config', e);
      setSaving(false);
    }
  };

  const handleClose = () => {
    setIsVisible(false);
    setTimeout(onClose, 300); // match transition duration
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className={\`absolute inset-0 bg-slate-950/80 backdrop-blur-sm transition-opacity duration-300 \${isVisible ? 'opacity-100' : 'opacity-0'}\`} 
        onClick={handleClose} 
      />
      
      {/* Modal Content */}
      <div 
        className={\`relative w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-slate-700 shadow-2xl rounded-2xl flex flex-col transition-all duration-300 ease-out transform \${isVisible ? 'opacity-100 translate-y-0 scale-100' : 'opacity-0 translate-y-8 scale-95'}\`}
      >
        {/* Header */}
        <div className="flex justify-between items-center p-6 border-b border-slate-800">
          <div className="flex items-center gap-3">
            <span className="text-2xl">⚙️</span>
            <div>
              <h2 className="text-lg font-black text-white italic tracking-tighter uppercase">HALCÓN CENTINELA Config</h2>
              <p className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-widest">Ajustes de Motor de Decisión</p>
            </div>
          </div>
          <button 
            onClick={handleClose}
            className="text-slate-500 hover:text-white transition-colors p-2"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6 scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-transparent">
          {loading ? (
            <div className="flex justify-center items-center py-20">
              <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
              {CONFIG_SECTIONS.map((section, idx) => (
                <div key={idx} className="bg-slate-800/30 p-5 rounded-xl border border-white/5">
                  <h3 className="text-xs font-black text-indigo-400 uppercase tracking-widest mb-4 border-b border-white/5 pb-2">
                    {section.title}
                  </h3>
                  <div className="space-y-4">
                    {section.keys.map((item) => (
                      <div key={item.key} className="flex flex-col gap-1.5">
                        <label className="text-[0.65rem] font-bold text-slate-400 uppercase tracking-wider">
                          {item.label}
                        </label>
                        <input
                          type={item.type}
                          value={config[item.key] !== undefined ? config[item.key] : ''}
                          onChange={(e) => handleChange(item.key, e.target.value)}
                          className="bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none transition-all"
                        />
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-800 flex justify-end gap-3 bg-slate-900/50 rounded-b-2xl">
          <button 
            onClick={handleClose}
            className="px-6 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest text-slate-400 hover:bg-slate-800 transition-colors"
          >
            Cancelar
          </button>
          <button 
            onClick={handleSave}
            disabled={saving || loading}
            className="px-8 py-2.5 rounded-xl text-xs font-black uppercase tracking-widest bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_15px_rgba(79,70,229,0.3)] transition-all flex items-center gap-2 disabled:opacity-50"
          >
            {saving ? (
              <>
                <div className="w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Guardando...
              </>
            ) : (
              'Guardar Cambios'
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
