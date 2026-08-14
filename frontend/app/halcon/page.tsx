'use client';
import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import HalconConfigModal from '@/components/HalconConfigModal';

interface HalconStatus {
  enabled: boolean;
  decisions_last_hour: number;
}

interface ScoreEvent {
  time: string;
  symbol: string;
  direction: string;
  score: number;
  semaforo: string;
  decision: string;
  executed: boolean;
}

interface DecisionEvent {
  time: string;
  symbol: string;
  action: string;
  reason: string;
}

interface OraculoEvent {
  time: string;
  currency: string;
  event: string;
  impact: string;
}

export default function HalconPage() {
  const [status, setStatus] = useState<HalconStatus>({ enabled: true, decisions_last_hour: 0 });
  const [scores, setScores] = useState<ScoreEvent[]>([]);
  const [decisions, setDecisions] = useState<DecisionEvent[]>([]);
  const [events, setEvents] = useState<OraculoEvent[]>([]);
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // In a real scenario, this would fetch from the backend
    // fetch('http://localhost:8080/api/v1/halcon/status')
    
    // Mocking the data for UI layout
    setStatus({ enabled: true, decisions_last_hour: 12 });
    
    setScores([
      { time: new Date().toISOString(), symbol: 'EURUSD', direction: 'LONG', score: 85, semaforo: 'VERDE', decision: 'OPEN_LONG', executed: true },
      { time: new Date(Date.now() - 5*60000).toISOString(), symbol: 'BTCUSDT', direction: 'SHORT', score: -45, semaforo: 'AMARILLO', decision: 'HOLD', executed: false },
      { time: new Date(Date.now() - 15*60000).toISOString(), symbol: 'GBPUSD', direction: 'SHORT', score: -92, semaforo: 'ROJO', decision: 'CLOSE_LONG', executed: true },
    ]);

    setDecisions([
      { time: new Date().toISOString(), symbol: 'EURUSD', action: 'OPEN_LONG', reason: 'Score 85 > threshold 75' },
      { time: new Date(Date.now() - 15*60000).toISOString(), symbol: 'GBPUSD', action: 'CLOSE_LONG', reason: 'Score -92 below exit threshold -50' },
    ]);

    setEvents([
      { time: new Date(Date.now() + 30*60000).toISOString(), currency: 'USD', event: 'NFP Data', impact: 'HIGH' },
      { time: new Date(Date.now() + 120*60000).toISOString(), currency: 'EUR', event: 'ECB Press Conference', impact: 'HIGH' },
    ]);
    
    setLoading(false);
  }, []);

  const toggleStatus = async () => {
    const newStatus = !status.enabled;
    setStatus({ ...status, enabled: newStatus });
    try {
      await fetch('http://localhost:8080/api/v1/halcon/toggle', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newStatus })
      });
    } catch (e) {
      console.error('Failed to toggle status', e);
    }
  };

  const getSemaforoColor = (color: string) => {
    switch(color) {
      case 'VERDE': return 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20';
      case 'ROJO': return 'text-rose-500 bg-rose-500/10 border-rose-500/20';
      case 'AMARILLO': return 'text-amber-500 bg-amber-500/10 border-amber-500/20';
      default: return 'text-slate-400 bg-slate-800 border-slate-700';
    }
  };

  return (
    <div className="space-y-8 pb-20 p-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2 text-[0.65rem] font-black text-slate-500 uppercase tracking-widest">
            <Link href="/" className="hover:text-blue-400">Home</Link>
            <span>/</span>
            <span className="text-slate-300">Sistemas</span>
          </div>
          <h1 className="text-3xl font-black italic tracking-tighter">HALCÓN CENTINELA</h1>
        </div>
      </div>

      {/* Status Card */}
      <div className="card glass-effect-premium border-white/5 p-6 relative overflow-hidden flex justify-between items-center">
        <div className="flex items-center gap-6">
          <div className={\`w-4 h-4 rounded-full \${status.enabled ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'}\`} />
          <div>
            <h2 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-1">Estado del Sistema</h2>
            <div className={\`text-2xl font-black italic tracking-tighter \${status.enabled ? 'text-emerald-400' : 'text-rose-400'}\`}>
              {status.enabled ? 'ACTIVO' : 'INACTIVO'}
            </div>
          </div>
        </div>
        
        <div className="text-right">
          <h2 className="text-[0.65rem] font-black text-slate-500 uppercase tracking-widest mb-1">Decisiones (Última hora)</h2>
          <div className="text-2xl font-black text-blue-400">{status.decisions_last_hour}</div>
        </div>

        <button 
          onClick={toggleStatus}
          className={\`px-6 py-2 rounded-xl text-xs font-black uppercase tracking-widest transition-all \${status.enabled ? 'bg-rose-500/10 text-rose-500 hover:bg-rose-500/20' : 'bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500/20'}\`}
        >
          {status.enabled ? 'Desactivar' : 'Activar'}
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-8">
        {/* Recent Scores Table */}
        <div className="card glass-effect border-slate-800/50 p-6">
          <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-6">Evaluaciones Recientes</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-white/5 text-[0.65rem] font-black text-slate-500 uppercase tracking-widest">
                  <th className="py-3 px-2">Time</th>
                  <th className="py-3 px-2">Symbol</th>
                  <th className="py-3 px-2">Dir</th>
                  <th className="py-3 px-2">Score</th>
                  <th className="py-3 px-2">Semáforo</th>
                  <th className="py-3 px-2">Decisión</th>
                  <th className="py-3 px-2">Exec</th>
                </tr>
              </thead>
              <tbody>
                {scores.map((score, i) => (
                  <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition-colors text-xs font-bold text-slate-300">
                    <td className="py-3 px-2 text-slate-500">{new Date(score.time).toLocaleTimeString()}</td>
                    <td className="py-3 px-2">{score.symbol}</td>
                    <td className={\`py-3 px-2 \${score.direction === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}\`}>{score.direction}</td>
                    <td className="py-3 px-2 font-mono">{score.score}</td>
                    <td className="py-3 px-2">
                      <span className={\`px-2 py-1 rounded-md text-[0.6rem] border \${getSemaforoColor(score.semaforo)}\`}>
                        {score.semaforo}
                      </span>
                    </td>
                    <td className="py-3 px-2">{score.decision}</td>
                    <td className="py-3 px-2">{score.executed ? '✅' : '❌'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-8">
          {/* Recent Decisions */}
          <div className="card glass-effect border-slate-800/50 p-6">
            <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest mb-6">Decisiones Ejecutadas</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-white/5 text-[0.65rem] font-black text-slate-500 uppercase tracking-widest">
                    <th className="py-3 px-2">Time</th>
                    <th className="py-3 px-2">Symbol</th>
                    <th className="py-3 px-2">Action</th>
                    <th className="py-3 px-2">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {decisions.map((dec, i) => (
                    <tr key={i} className="border-b border-white/5 hover:bg-white/5 transition-colors text-xs font-bold text-slate-300">
                      <td className="py-3 px-2 text-slate-500">{new Date(dec.time).toLocaleTimeString()}</td>
                      <td className="py-3 px-2">{dec.symbol}</td>
                      <td className="py-3 px-2 text-blue-400">{dec.action}</td>
                      <td className="py-3 px-2 text-[0.65rem] text-slate-400 truncate max-w-[200px]" title={dec.reason}>{dec.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* ORÁCULO Events */}
          <div className="card glass-effect border-slate-800/50 p-6">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-sm font-black text-slate-400 uppercase tracking-widest">Eventos ORÁCULO</h3>
              <span className="text-xs">👁️</span>
            </div>
            <div className="space-y-3">
              {events.map((evt, i) => (
                <div key={i} className="flex justify-between items-center bg-slate-900/50 p-3 rounded-xl border border-white/5">
                  <div>
                    <div className="text-xs font-bold text-white mb-1">{evt.event}</div>
                    <div className="flex gap-2 text-[0.6rem] font-black uppercase tracking-widest">
                      <span className="text-slate-400">{evt.currency}</span>
                      <span className="text-slate-600">•</span>
                      <span className={\`\${evt.impact === 'HIGH' ? 'text-rose-400' : 'text-amber-400'}\`}>{evt.impact} IMPACT</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-black text-blue-400 font-mono">{new Date(evt.time).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
                    <div className="text-[0.55rem] text-slate-500 uppercase font-black">Próximamente</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Floating Config Button */}
      <button 
        onClick={() => setIsConfigOpen(true)}
        className="fixed bottom-8 right-8 w-14 h-14 bg-indigo-600 hover:bg-indigo-500 text-white rounded-full flex items-center justify-center shadow-[0_0_20px_rgba(79,70,229,0.4)] transition-all hover:scale-110 z-40"
      >
        <span className="text-2xl">⚙️</span>
      </button>

      {/* Config Modal */}
      {isConfigOpen && (
        <HalconConfigModal onClose={() => setIsConfigOpen(false)} />
      )}

      <style jsx>{\`
        .glass-effect {
          background: rgba(17, 24, 39, 0.45);
          backdrop-filter: blur(16px);
          border: 1px solid rgba(255, 255, 255, 0.08);
          box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        }
        .glass-effect-premium {
          background: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.01) 100%);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255, 255, 255, 0.1);
          box-shadow: 0 10px 40px -10px rgba(0, 0, 0, 0.5);
        }
      \`}</style>
    </div>
  );
}
