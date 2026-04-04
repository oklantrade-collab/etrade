const API_BASE = ''  // Usar rewrites de Next.js como proxy al backend (evita CORS)

export async function apiFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}))
    throw new Error(errorData.detail || `API error: ${res.status}`)
  }
  return res.json()
}

// Auth API
export const login = (data: any) => apiFetch<any>('/api/v1/auth/login', { method: 'POST', body: JSON.stringify(data) })
export const register = (data: any) => apiFetch<any>('/api/v1/auth/register', { method: 'POST', body: JSON.stringify(data) })
export const verifyEmail = (token: string) => apiFetch<any>(`/api/v1/auth/verify/${token}`)
export const forgotPassword = (data: any) => apiFetch<any>('/api/v1/auth/forgot-password', { method: 'POST', body: JSON.stringify(data) })
export const resetPassword = (data: any) => apiFetch<any>('/api/v1/auth/reset-password', { method: 'POST', body: JSON.stringify(data) })
export const getMe = () => apiFetch<any>('/api/v1/auth/me')
export const logoutUser = () => apiFetch<any>('/api/v1/auth/logout', { method: 'POST' })

// Admin API
export const getAdminRoles = () => apiFetch<any>('/api/v1/admin/roles')
export const updateAdminRole = (id: number, data: any) => apiFetch<any>(`/api/v1/admin/roles/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const createAdminRole = (data: any) => apiFetch<any>('/api/v1/admin/roles', { method: 'POST', body: JSON.stringify(data) })
export const getAdminUsers = () => apiFetch<any>('/api/v1/admin/users')
export const updateAdminUser = (id: string, data: any) => apiFetch<any>(`/api/v1/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) })

// Dashboard
export const getDashboardSummary = () => apiFetch<any>('/api/v1/dashboard/summary')

// Market
export const getSymbols = () => apiFetch<any>('/api/v1/market/symbols')
export const getCandles = (symbol: string, timeframe = '15m', limit = 100) =>
  apiFetch<any>(`/api/v1/market/candles/${encodeURIComponent(symbol)}?timeframe=${timeframe}&limit=${limit}`)
export const getIndicators = (symbol: string, timeframe = '15m') =>
  apiFetch<any>(`/api/v1/market/indicators/${encodeURIComponent(symbol)}?timeframe=${timeframe}`)

// Signals
export const getSignals = (params?: { status?: string; symbol?: string; limit?: number }) => {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.symbol) qs.set('symbol', params.symbol)
  if (params?.limit) qs.set('limit', String(params.limit))
  return apiFetch<any>(`/api/v1/signals?${qs}`)
}
export const getSpikes = (limit = 50) => apiFetch<any>(`/api/v1/signals/spikes?limit=${limit}`)
export const getSignalMtfDetail = (signalId: string) => apiFetch<any>(`/api/v1/signals/${signalId}/mtf-detail`)

// Positions
export const getPositions = (status?: string) =>
  apiFetch<any>(`/api/v1/positions${status ? `?status=${status}` : ''}`)
export const closePosition = (id: string) =>
  apiFetch<any>(`/api/v1/positions/${id}/close`, { method: 'DELETE' })
export const getOrders = (params?: { status?: string; symbol?: string }) => {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.symbol) qs.set('symbol', params.symbol)
  return apiFetch<any>(`/api/v1/positions/orders?${qs}`)
}

// Risk
export const getRiskConfig = () => apiFetch<any>('/api/v1/risk/config')
export const updateRiskConfig = (data: Record<string, any>) =>
  apiFetch<any>('/api/v1/risk/config', { method: 'PUT', body: JSON.stringify(data) })
export const activateKillSwitch = () =>
  apiFetch<any>('/api/v1/risk/kill-switch', { method: 'POST' })

// Logs
export const getLogs = (params?: { module?: string; level?: string; cycle_id?: string; limit?: number }) => {
  const qs = new URLSearchParams()
  if (params?.module) qs.set('module', params.module)
  if (params?.level) qs.set('level', params.level)
  if (params?.cycle_id) qs.set('cycle_id', params.cycle_id)
  if (params?.limit) qs.set('limit', String(params.limit))
  return apiFetch<any>(`/api/v1/logs?${qs}`)
}
export const getCycles = (limit = 20) => apiFetch<any>(`/api/v1/cycles?limit=${limit}`)

// Backtests
export const getBacktests = () => apiFetch<any>('/api/v1/backtests')
export const runBacktest = (data: Record<string, any>) =>
  apiFetch<any>('/api/v1/backtests/run', { method: 'POST', body: JSON.stringify(data) })
