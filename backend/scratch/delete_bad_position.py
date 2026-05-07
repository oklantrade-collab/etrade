from app.core.supabase_client import get_supabase

sb = get_supabase()
position_id = "a19427a0-2064-47a3-95df-6af293a17666"

print(f"Attempting to delete position {position_id}...")
res = sb.table("forex_positions").delete().eq("id", position_id).execute()

if res.data:
    print(f"Successfully deleted position: {res.data}")
else:
    print("Could not find or delete position.")
