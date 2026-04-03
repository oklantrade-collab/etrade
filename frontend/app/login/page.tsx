'use client'
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { login } from '@/lib/api-client'

export default function LoginPage() {
  const [correo, setCorreo] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const router = useRouter()

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    
    try {
      await login({ correo, password })
      router.push('/portfolio')
    } catch (err: any) {
      setError(err.message || 'Error al iniciar sesión. Verifica tus credenciales.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05070a] relative overflow-hidden">
      {/* Background Decorative Elements */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-emerald-500/5 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-500/5 blur-[120px] rounded-full" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full opacity-[0.03]" 
             style={{ backgroundImage: 'radial-gradient(#fff 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
      </div>

      <div className="w-full max-w-md p-6 relative z-10">
        {/* Logo Section */}
        <div className="text-center mb-10 animate-in fade-in slide-in-from-bottom-4 duration-1000">
          <div className="inline-block p-3 rounded-2xl bg-gradient-to-br from-emerald-500/20 to-emerald-800/10 border border-emerald-500/20 mb-4 shadow-2xl shadow-emerald-500/10">
            <h1 className="text-4xl font-extrabold tracking-tighter text-white" style={{ fontFamily: 'var(--font-serif, serif)' }}>
              eTrade<span className="text-emerald-500">.</span>
            </h1>
          </div>
          <p className="text-slate-500 text-[0.65rem] uppercase tracking-[0.4em] font-bold">Premium Financial Systems</p>
        </div>

        {/* Card */}
        <div className="bg-[#0c0f16]/80 backdrop-blur-xl border border-white/5 rounded-3xl p-8 shadow-2xl shadow-black animate-in fade-in zoom-in-95 duration-700">
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-white mb-2">Bienvenido</h2>
            <p className="text-slate-400 text-sm">Ingresa tus credenciales para acceder a la plataforma.</p>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            {error && (
              <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-medium animate-in shake duration-300">
                {error}
              </div>
            )}

            <div className="space-y-1.5">
              <label className="text-[0.7rem] font-bold text-slate-500 uppercase tracking-widest ml-1">Correo Electrónico</label>
              <input 
                type="email" 
                value={correo}
                onChange={e => setCorreo(e.target.value)}
                className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-12 text-white text-sm focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20 transition-all placeholder:text-slate-700"
                placeholder="ejemplo@etrade.com"
                required
              />
            </div>

            <div className="space-y-1.5">
              <div className="flex justify-between items-center px-1">
                <label className="text-[0.7rem] font-bold text-slate-500 uppercase tracking-widest">Contraseña</label>
                <Link href="/auth/forgot-password" className="text-[0.65rem] text-emerald-500/70 hover:text-emerald-500 font-bold transition-colors">
                  ¿Olvidaste tu contraseña?
                </Link>
              </div>
              <input 
                type="password" 
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-12 text-white text-sm focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/20 transition-all placeholder:text-slate-700"
                placeholder="••••••••"
                required
              />
            </div>

            <button 
              type="submit" 
              disabled={loading}
              className="w-full h-12 mt-4 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-bold rounded-xl transition-all active:scale-[0.98] flex items-center justify-center shadow-lg shadow-emerald-500/20"
            >
              {loading ? (
                <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" />
              ) : (
                'Iniciar Sesión'
              )}
            </button>
          </form>

          <div className="mt-8 pt-6 border-t border-white/5 text-center">
            <p className="text-slate-500 text-xs">
              ¿No tienes cuenta?{' '}
              <Link href="/register" className="text-emerald-500 hover:text-emerald-400 font-bold transition-colors">
                Regístrate aquí
              </Link>
            </p>
          </div>
        </div>

        {/* Footer */}
        <p className="mt-10 text-center text-slate-700 text-[0.65rem] font-medium tracking-widest">
          EST. 2026 · ETRADE INSTITUTIONAL · SECURE ACCESS
        </p>
      </div>

      <style jsx>{`
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          20%, 60% { transform: translateX(-5px); }
          40%, 80% { transform: translateX(5px); }
        }
        .animate-shake {
          animation: shake 0.4s ease-in-out;
        }
      `}</style>
    </div>
  )
}
