import httpx
h = {
    'apikey': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlyaW90bnNvYXVxcmZzamJxeXlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM0MTI3NzcsImV4cCI6MjA4ODk4ODc3N30.Q66IwV3GhiiKT7h6Wuy8T--KWtw0wlRj0siKg68sBo0',
    'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlyaW90bnNvYXVxcmZzamJxeXlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM0MTI3NzcsImV4cCI6MjA4ODk4ODc3N30.Q66IwV3GhiiKT7h6Wuy8T--KWtw0wlRj0siKg68sBo0'
}
r = httpx.get('https://iriotnsoauqrfsjbqyyp.supabase.co/rest/v1/system_logs?level=eq.ERROR&order=created_at.desc&limit=20', headers=h).json()
for log in r:
    print(f"{log['created_at']} | {log['module']} | {log['message']}")
