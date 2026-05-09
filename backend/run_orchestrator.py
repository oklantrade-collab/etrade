import asyncio
import os
import sys

# Añadir el directorio actual al path para importar 'app'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.stocks.stocks_orchestrator import run_orchestrator_cycle

async def main():
    print("\n" + "="*50)
    print("🚀 APEX ORCHESTRATOR — CICLO MANUAL")
    print("="*50)
    
    try:
        supabase = get_supabase()
        print("📡 Conectado a Supabase. Evaluando mercado...")
        
        await run_orchestrator_cycle(supabase)
        
        print("\n" + "="*50)
        print("✅ CICLO COMPLETADO")
        print("="*50)
        print("📊 Revisa stocks_priority_queue en Supabase")
        print("📊 Dashboard: http://localhost:3000/stocks/opportunities")
        print("="*50 + "\n")
        
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
