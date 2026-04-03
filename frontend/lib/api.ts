const API_BASE = process.env.NEXT_PUBLIC_API_URL
  || 'http://localhost:8000'

export const api = {
  get: async (path: string) => {
    const res = await fetch(`${API_BASE}${path}`)
    if (!res.ok) throw new Error(
      `API Error: ${res.status}`
    )
    return res.json()
  },
  post: async (path: string, body: any) => {
    const res = await fetch(`${API_BASE}${path}`, {
      method:  'POST',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify(body),
    })
    if (!res.ok) throw new Error(
      `API Error: ${res.status}`
    )
    return res.json()
  },
  put: async (path: string, body: any) => {
    const res = await fetch(`${API_BASE}${path}`, {
      method:  'PUT',
      headers: {'Content-Type': 'application/json'},
      body:    JSON.stringify(body),
    })
    if (!res.ok) throw new Error(
      `API Error: ${res.status}`
    )
    return res.json()
  },
}
