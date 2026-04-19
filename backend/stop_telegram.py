
from app.core.supabase_client import get_supabase
sb = get_supabase()
res = sb.table('trading_config').select('*').eq('id', 1).maybe_single().execute()
print(f"TELEGRAM_ENABLED: {res.data.get('telegram_enabled')}")

# Desactivar telegram_enabled para frenar el flood si el bot lo lee en cada ciclo
sb.table('trading_config').update({'telegram_enabled': False}).eq('id', 1).execute()
print("Telegram desactivado en DB.")
