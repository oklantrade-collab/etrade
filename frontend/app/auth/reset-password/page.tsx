'use client'
import React, { useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { resetPassword } from '@/lib/api-client'
import Link from 'next/link'

export default function ResetPasswordPage() {
  const searchParams = useSearchParams()
  const token = searchParams.get('token')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')
  const router = useRouter()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (newPassword !== confirmPassword) {
      setError('Las contraseñas no coinciden.')
      return
    }
    if (!token) {
      setError('Token inválido.')
      return
    }

    setLoading(true)
    setError('')
    try {
      const res = await resetPassword({ token, new_password: newPassword })
      setSuccess(res.message)
      setTimeout(() => router.push('/login'), 3000)
    } catch (err: any) {
      setError(err.message || 'Error al restablecer la contraseña.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05070a] relative overflow-hidden">
      <div className="w-full max-w-md p-6 relative z-10 transition-all">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-black text-white italic tracking-tighter">eTrade<span className="text-emerald-500">.</span></h1>
          <p className="text-[0.65rem] text-slate-500 uppercase tracking-[0.4em] font-bold mt-2">Seguridad de Acceso</p>
        </div>

        <div className="bg-[#0c0f16]/90 backdrop-blur-xl border border-white/5 rounded-3xl p-8 shadow-2xl">
          {success ? (
            <div className="text-center py-6">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-emerald-500/10 text-emerald-500 rounded-full mb-6 text-2xl">✅</div>
              <h2 className="text-xl font-bold text-white mb-4">Contraseña Actualizada</h2>
              <p className="text-slate-400 text-sm leading-relaxed mb-8">{success}</p>
              <Link href="/login" className="text-emerald-500 font-bold text-sm hover:underline">Iniciar Sesión Ahora</Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="mb-6">
                <h2 className="text-xl font-bold text-white mb-2">Nueva Contraseña</h2>
                <p className="text-slate-500 text-xs leading-relaxed">Define una nueva clave de acceso institucional.</p>
              </div>

              {error && <div className="p-3 bg-red-500/10 border border-red-500/20 text-red-500 text-xs rounded-xl">{error}</div>}

              <div className="space-y-4">
                <div className="space-y-1.5">
                  <label className="text-[0.7rem] font-bold text-slate-500 uppercase tracking-widest ml-1">Nueva Contraseña</label>
                  <input 
                    type="password" required minLength={8}
                    value={newPassword} onChange={e => setNewPassword(e.target.value)}
                    className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-12 text-white text-sm focus:border-emerald-500/50 outline-none transition-all"
                    placeholder="••••••••"
                  />
                </div>
                <div className="space-y-1.5">
                  <label className="text-[0.7rem] font-bold text-slate-500 uppercase tracking-widest ml-1">Confirmar Nueva Contraseña</label>
                  <input 
                    type="password" required minLength={8}
                    value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                    className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-12 text-white text-sm focus:border-emerald-500/50 outline-none transition-all"
                    placeholder="••••••••"
                  />
                </div>
              </div>

              <button 
                type="submit" disabled={loading}
                className="w-full h-12 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold rounded-xl transition-all shadow-lg shadow-emerald-500/10"
              >
                {loading ? 'Procesando...' : 'Guardar Nueva Contraseña'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
