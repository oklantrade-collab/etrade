'use client'
import React, { useState } from 'react'
import { forgotPassword } from '@/lib/api-client'
import Link from 'next/link'

export default function ForgotPasswordPage() {
  const [correo, setCorreo] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const res = await forgotPassword({ correo })
      setSuccess(res.message)
    } catch (err: any) {
      setError(err.message || 'Error al procesar la solicitud.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05070a] relative overflow-hidden">
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none opacity-10">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-full h-full" 
             style={{ backgroundImage: 'radial-gradient(circle, #10b981 1px, transparent 1px)', backgroundSize: '60px 60px' }} />
      </div>

      <div className="w-full max-w-md p-6 relative z-10 transition-all">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-black text-white italic tracking-tighter">eTrade<span className="text-emerald-500">.</span></h1>
          <p className="text-[0.65rem] text-slate-500 uppercase tracking-[0.4em] font-bold mt-2">Recuperación de Acceso</p>
        </div>

        <div className="bg-[#0c0f16]/90 backdrop-blur-xl border border-white/5 rounded-3xl p-8 shadow-2xl">
          {success ? (
            <div className="text-center py-6">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-500/10 text-emerald-500 rounded-full mb-6 text-2xl">📧</div>
              <h2 className="text-xl font-bold text-white mb-4">Correo Enviado</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-8">{success}</p>
              <Link href="/login" className="text-emerald-500 font-bold text-sm hover:underline">Volver al inicio</Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <h2 className="text-xl font-bold text-white mb-2">Restablecer Contraseña</h2>
                <p className="text-slate-500 text-xs leading-relaxed">Ingresa tu correo electrónico y te enviaremos un enlace seguro para crear una nueva contraseña.</p>
              </div>

              {error && <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-500 text-xs rounded-xl">{error}</div>}

              <div className="space-y-1.5">
                <label className="text-[0.7rem] font-bold text-slate-500 uppercase tracking-widest ml-1">Correo Electrónico</label>
                <input 
                  type="email" required
                  value={correo} onChange={e => setCorreo(e.target.value)}
                  className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-12 text-white text-sm focus:border-emerald-500/50 outline-none transition-all"
                  placeholder="ejemplo@etrade.com"
                />
              </div>

              <button 
                type="submit" disabled={loading}
                className="w-full h-12 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold rounded-xl transition-all shadow-lg shadow-emerald-500/10"
              >
                {loading ? 'Procesando...' : 'Enviar Enlace de Recuperación'}
              </button>

              <div className="text-center pt-2">
                <Link href="/login" className="text-slate-500 hover:text-white text-xs font-medium transition-colors">
                  Cancelar y volver
                </Link>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
