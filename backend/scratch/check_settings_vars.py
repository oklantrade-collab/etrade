import os, sys
sys.path.append(os.path.join(os.getcwd(), 'backend'))
from app.core.config import settings

print(f"SETTINGS SUPABASE_URL: {settings.supabase_url}")
print(f"SETTINGS SUPABASE_SERVICE_KEY: {settings.supabase_service_key[:10]}...")
