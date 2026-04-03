'use client'
import React, { useEffect, useState } from 'react'
import { getAdminRoles, updateAdminRole, createAdminRole, getAdminUsers, updateAdminUser } from '@/lib/api-client'

export default function AdminPanel() {
  const [roles, setRoles] = useState<any[]>([])
  const [users, setUsers] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [editingRole, setEditingRole] = useState<any>(null)
  const [newCode, setNewCode] = useState('')
  const [confirmCode, setConfirmCode] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isNewRoleModalOpen, setIsNewRoleModalOpen] = useState(false)
  const [newRoleData, setNewRoleData] = useState({ nombre: '', codigo_registro: '', descripcion: '' })

  const loadData = async () => {
    setLoading(true)
    try {
      const [rolesData, usersData] = await Promise.all([
        getAdminRoles(),
        getAdminUsers()
      ])
      setRoles(rolesData)
      setUsers(usersData)
    } catch (err) {
      console.error('Error loading admin data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleEditRole = (role: any) => {
    setEditingRole(role)
    setNewCode(role.codigo_registro)
    setConfirmCode(role.codigo_registro)
    setIsModalOpen(true)
  }

  const saveRoleCode = async () => {
    if (newCode !== confirmCode) {
      alert('Los códigos no coinciden')
      return
    }
    if (newCode.length < 6) {
      alert('El código debe tener al menos 6 caracteres')
      return
    }

    try {
      await updateAdminRole(editingRole.id, { codigo_registro: newCode })
      setIsModalOpen(false)
      loadData()
    } catch (err: any) {
      alert(err.message || 'Error al actualizar el código')
    }
  }

  const handleCreateRole = async () => {
    try {
      await createAdminRole(newRoleData)
      setIsNewRoleModalOpen(false)
      setNewRoleData({ nombre: '', codigo_registro: '', descripcion: '' })
      loadData()
    } catch (err: any) {
      alert(err.message || 'Error al crear el rol')
    }
  }

  const toggleUserStatus = async (user: any) => {
    try {
      await updateAdminUser(user.id, { activo: !user.activo })
      loadData()
    } catch (err: any) {
      alert(err.message || 'Error al actualizar usuario')
    }
  }

  if (loading) return <div className="p-10 text-center text-slate-500 animate-pulse">Cargando panel de administración...</div>

  return (
    <div className="space-y-12 animate-in fade-in duration-500">
      
      {/* SECCIÓN: ROLES Y CÓDIGOS */}
      <section className="space-y-6">
        <div className="flex justify-between items-end">
          <div>
            <h3 className="text-xl font-bold text-white mb-1">Gestión de Perfiles y Roles</h3>
            <p className="text-xs text-slate-500 uppercase tracking-widest">Códigos de Registro y Control de Acceso</p>
          </div>
          <button 
            onClick={() => setIsNewRoleModalOpen(true)}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-lg transition-all shadow-lg shadow-emerald-500/10"
          >
            + AGREGAR ROL
          </button>
        </div>

        <div className="card glass-effect overflow-hidden !p-0">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="bg-white/[0.03] border-b border-white/5 text-slate-500 font-bold uppercase tracking-widest">
                <th className="px-6 py-4">Rol</th>
                <th className="px-6 py-4">Código de Registro</th>
                <th className="px-6 py-4 text-center">Usuarios Activos</th>
                <th className="px-6 py-4 text-right">Acciones</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {roles.map(role => (
                <tr key={role.id} className="hover:bg-white/[0.01] transition-colors">
                  <td className="px-6 py-4">
                    <span className="font-bold text-white text-sm">{role.nombre}</span>
                    <p className="text-[10px] text-slate-500 mt-0.5">{role.descripcion}</p>
                  </td>
                  <td className="px-6 py-4">
                    <code className="bg-black/40 px-3 py-1.5 rounded-lg border border-white/5 text-emerald-500 font-mono font-bold tracking-widest">
                      {role.codigo_registro}
                    </code>
                  </td>
                  <td className="px-6 py-4 text-center">
                    <span className="inline-flex items-center justify-center min-w-[24px] h-6 px-2 bg-emerald-500/10 text-emerald-500 rounded-full font-black">
                      {role.usuarios_activos}
                    </span>
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button 
                      onClick={() => handleEditRole(role)}
                      className="p-2 bg-white/5 hover:bg-white/10 rounded-lg text-slate-400 hover:text-white transition-all"
                      title="Editar código"
                    >
                      ✏️
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* SECCIÓN: LISTA DE USUARIOS */}
      <section className="space-y-6">
        <div>
          <h3 className="text-xl font-bold text-white mb-1">Directorio de Usuarios</h3>
          <p className="text-xs text-slate-500 uppercase tracking-widest">Usuarios registrados y estado de verificación</p>
        </div>

        <div className="card glass-effect overflow-hidden !p-0">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="bg-white/[0.03] border-b border-white/5 text-slate-500 font-bold uppercase tracking-widest">
                <th className="px-6 py-4">Usuario</th>
                <th className="px-6 py-4">Correo</th>
                <th className="px-6 py-4">Rol</th>
                <th className="px-6 py-4">Estado</th>
                <th className="px-6 py-4">Fecha Reg.</th>
                <th className="px-6 py-4 text-right">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 font-medium">
              {users.map(user => (
                <tr key={user.id} className={`${!user.activo ? 'opacity-50' : ''} hover:bg-white/[0.01] transition-colors`}>
                  <td className="px-6 py-4 font-bold text-white">{user.nombre}</td>
                  <td className="px-6 py-4 text-slate-400">{user.correo}</td>
                  <td className="px-6 py-4">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-black italic ${user.roles?.nombre === 'CEO' ? 'bg-amber-500/10 text-amber-500' : 'bg-blue-500/10 text-blue-500'}`}>
                      {user.roles?.nombre}
                    </span>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex flex-col gap-1">
                      <span className={`text-[9px] font-bold ${user.verificado ? 'text-emerald-500' : 'text-amber-500'}`}>
                        {user.verificado ? '● VERIFICADO' : '○ PENDIENTE'}
                      </span>
                      <span className={`text-[9px] font-bold ${user.activo ? 'text-blue-500' : 'text-rose-500'}`}>
                        {user.activo ? '● ACTIVO' : '○ DESACTIVADO'}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 text-slate-500">
                    {new Date(user.fecha_registro).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <button 
                      onClick={() => toggleUserStatus(user)}
                      className={`px-3 py-1 rounded text-[9px] font-black uppercase transition-all ${user.activo ? 'bg-rose-500/10 text-rose-500 hover:bg-rose-500 hover:text-white' : 'bg-emerald-500/10 text-emerald-500 hover:bg-emerald-500 hover:text-white'}`}
                    >
                      {user.activo ? 'Desactivar' : 'Activar'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {users.length === 0 && <div className="p-10 text-center text-slate-600 italic">No hay usuarios registrados aún.</div>}
        </div>
      </section>

      {/* MODAL: EDITAR CÓDIGO */}
      {isModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 backdrop-blur-md bg-black/60 animate-in fade-in duration-300">
          <div className="bg-[#0c0f16] border border-white/10 rounded-3xl p-8 max-w-sm w-full shadow-2xl animate-in zoom-in-95 duration-300">
            <h4 className="text-lg font-bold text-white mb-2">Editar Código: {editingRole?.nombre}</h4>
            <p className="text-xs text-slate-500 mb-6 font-medium">Define el nuevo código de invitación para este rol.</p>
            
            <div className="space-y-4">
              <div className="form-group">
                <label className="text-[10px] text-slate-500 uppercase font-black tracking-widest block mb-1">Nuevo Código</label>
                <input 
                  type="text" 
                  className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-emerald-500 font-bold tracking-widest font-mono" 
                  value={newCode} onChange={(e) => setNewCode(e.target.value)} 
                />
              </div>
              <div className="form-group">
                <label className="text-[10px] text-slate-500 uppercase font-black tracking-widest block mb-1">Confirmar Código</label>
                <input 
                  type="text" 
                  className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-emerald-500 font-bold tracking-widest font-mono" 
                  value={confirmCode} onChange={(e) => setConfirmCode(e.target.value)} 
                />
              </div>
              
              <div className="flex gap-3 pt-4">
                <button onClick={() => setIsModalOpen(false)} className="flex-1 px-4 py-3 bg-white/5 hover:bg-white/10 text-white text-xs font-bold rounded-xl transition-all">CANCELAR</button>
                <button onClick={saveRoleCode} className="flex-1 px-4 py-3 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl transition-all shadow-lg shadow-emerald-500/20">GUARDAR</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* MODAL: NUEVO ROL */}
      {isNewRoleModalOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-6 backdrop-blur-md bg-black/60 animate-in fade-in duration-300">
          <div className="bg-[#0c0f16] border border-white/10 rounded-3xl p-8 max-w-sm w-full shadow-2xl">
            <h4 className="text-lg font-bold text-white mb-2">Crear Nuevo Perfil</h4>
            <p className="text-xs text-slate-500 mb-6 font-medium">Añade un nuevo rol de acceso al sistema.</p>
            
            <div className="space-y-4">
              <div className="form-group">
                <label className="text-[10px] text-slate-500 uppercase font-black tracking-widest block mb-1">Nombre del Rol</label>
                <input 
                  type="text" 
                  className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-white" 
                  value={newRoleData.nombre} onChange={(e) => setNewRoleData({...newRoleData, nombre: e.target.value})}
                  placeholder="ej. Analista"
                />
              </div>
              <div className="form-group">
                <label className="text-[10px] text-slate-500 uppercase font-black tracking-widest block mb-1">Código de Registro</label>
                <input 
                  type="text" 
                  className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-emerald-500 font-bold tracking-widest font-mono" 
                  value={newRoleData.codigo_registro} onChange={(e) => setNewRoleData({...newRoleData, codigo_registro: e.target.value})}
                />
              </div>
              <div className="form-group">
                <label className="text-[10px] text-slate-500 uppercase font-black tracking-widest block mb-1">Descripción</label>
                <input 
                  type="text" 
                  className="w-full bg-black/40 border border-white/5 rounded-xl px-4 h-11 text-slate-300"
                  value={newRoleData.descripcion} onChange={(e) => setNewRoleData({...newRoleData, descripcion: e.target.value})}
                />
              </div>
              
              <div className="flex gap-3 pt-4">
                <button onClick={() => setIsNewRoleModalOpen(false)} className="flex-1 px-4 py-3 bg-white/5 hover:bg-white/10 text-white text-xs font-bold rounded-xl transition-all">CANCELAR</button>
                <button onClick={handleCreateRole} className="flex-1 px-4 py-3 bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold rounded-xl transition-all shadow-lg shadow-emerald-500/20">CREAR ROL</button>
              </div>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .glass-effect {
          background: rgba(17, 24, 39, 0.4);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
          border: 1px solid rgba(255, 255, 255, 0.05);
        }
      `}</style>
    </div>
  )
}
