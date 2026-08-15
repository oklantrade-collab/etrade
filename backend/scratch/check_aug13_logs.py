from app.core.supabase_client import get_supabase

sb = get_supabase()

# Consultar system_logs alrededor del 13 de agosto de 2026
logs = sb.table('system_logs').select('*').gte('created_at', '2026-08-13T15:00:00').lte('created_at', '2026-08-13T19:00:00').order('created_at', desc=False).limit(100).execute()

print(f"Total logs encontrados entre 15:00 y 19:00 UTC el 13 de agosto: {len(logs.data)}")
for l in logs.data:
    print(f"[{l.get('created_at')}] [{l.get('module')}] [{l.get('level')}]: {l.get('message')}")
    if l.get('context'):
        print(f"   Context: {l.get('context')}")
