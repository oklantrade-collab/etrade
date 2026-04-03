'use client'
import React, { useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { register } from '@/lib/api-client'

export default function RegisterPage() {
  const [formData, setFormData] = useState({
    nombre: '',
    correo: '',
    password: '',
    confirm_password: '',
    codigo_registro: ''
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const router = useRouter()

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value })
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setError('')
    setSuccess('')
    
    try {
      const res = await register(formData)
      setSuccess(res.message || 'Registro exitoso. Revisa tu correo.')
      setTimeout(() => router.push('/login'), 3000)
    } catch (err: any) {
      setError(err.message || 'Error al completar el registro.')
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#05070a] relative overflow-hidden">
      {/* Background Decor */}
      <div className="absolute top-0 left-0 w-full h-full pointer-events-none">
        <div className="absolute top-[-10%] right-[-10%] w-[40%] h-[40%] bg-blue-500/5 blur-[120px] rounded-full" />
        <div className="absolute bottom-[-10%] left-[-10%] w-[40%] h-[40%] bg-emerald-500/5 blur-[120px] rounded-full" />
      </div>

      <div className="w-full max-w-lg p-6 relative z-10 animate-in fade-in slide-in-from-bottom-8 duration-700">
        <div className="text-center mb-8">
            <h1 className="text-3xl font-extrabold tracking-tighter text-white mb-2" style={{ fontFamily: 'var(--font-serif, serif)' }}>
              Crea tu cuenta <span className="text-emerald-500">eTrade</span>
            </h1>
            <p className="text-slate-500 text-xs font-semibold tracking-widest uppercase">REGISTRO DE NUEVO USUARIO</p>
        </div>

        <div className="bg-[#0c0f16]/80 backdrop-blur-xl border border-white/5 rounded-3xl p-8 shadow-2xl shadow-black">
          {success ? (
            <div className="text-center py-10">
              <div className="w-16 h-16 bg-emerald-500/20 rounded-full flex items-center justify-center mx-auto mb-6 text-emerald-500 text-3xl">✓</div>
              <h2 className="text-2xl font-bold text-white mb-4">¡Registro Exitoso!</h2>
              <p className="text-slate-400 text-sm mb-8 leading-relaxed">
                Hemos enviado un correo de verificación a <b>{formData.correo}</b>. 
                Por favor actívala para poder ingresar.
              </p>
              <Link href="/login" className="text-emerald-500 hover:text-emerald-400 font-bold transition-colors">
                Ir al Inicio de Sesión
              </Link>
            </div>
          ) : (
            <form onSubmit={handleRegister} className="space-y-6">
              {error && (
                <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-medium animate-in shake duration-300">
                  {error}
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-1.5 col-span-2">
                  <label className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-widest ml-1">Nombre Completo</label>
                  <input 
                    type="text" name="nombre" required
                    value={formData.nombre} onChange={handleChange}
                    className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-white text-sm focus:border-emerald-500/50 transition-all"
                    placeholder="Juan Pérez"
                  />
                </div>

                <div className="space-y-1.5 col-span-2">
                  <label className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-widest ml-1">Correo Electrónico</label>
                  <input 
                    type="email" name="correo" required
                    value={formData.correo} onChange={handleChange}
                    className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-white text-sm focus:border-emerald-500/50 transition-all"
                    placeholder="juan@ejemplo.com"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-widest ml-1">Contraseña</label>
                  <input 
                    type="password" name="password" required
                    value={formData.password} onChange={handleChange}
                    className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-white text-sm focus:border-emerald-500/50 transition-all"
                    placeholder="••••••••"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-widest ml-1">Confirmar</label>
                  <input 
                    type="password" name="confirm_password" required
                    value={formData.confirm_password} onChange={handleChange}
                    className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-white text-sm focus:border-emerald-500/50 transition-all"
                    placeholder="••••••••"
                  />
                </div>

                <div className="space-y-1.5 col-span-2">
                  <div className="flex justify-between items-center px-1">
                    <label className="text-[0.65rem] font-bold text-slate-500 uppercase tracking-widest">Código de Registro</label>
                    <span className="text-[0.6rem] text-slate-600 italic">Mandatorio para asignar ROL</span>
                  </div>
                  <input 
                    type="text" name="codigo_registro" required
                    value={formData.codigo_registro} onChange={handleChange}
                    className="w-full bg-emerald-500/5 border border-emerald-500/10 rounded-xl px-4 h-11 text-emerald-500 text-sm font-bold tracking-widest focus:border-emerald-500/50 transition-all placeholder:text-emerald-500/20"
                    placeholder="ETRADE-XXX"
                  />
                </div>
              </div>

              <button 
                type="submit" 
                disabled={loading}
                className="w-full h-12 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-bold rounded-xl transition-all shadow-lg shadow-emerald-500/20 flex items-center justify-center transform hover:scale-[1.01] active:scale-[0.99]"
              >
                {loading ? <div className="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin" /> : 'Crear Cuenta Institucional'}
              </button>
            </form>
          )}

          <div className="mt-8 pt-6 border-t border-white/5 text-center">
            <p className="text-slate-500 text-xs">
              ¿Ya tienes una cuenta?{' '}
              <Link href="/login" className="text-emerald-500 hover:text-emerald-400 font-bold transition-colors">
                Iniciar Sesión
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
