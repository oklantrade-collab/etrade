import os
import sys
from datetime import datetime, timezone, timedelta
from supabase import create_client

# Resolve paths to use eTrade env
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import dotenv
dotenv.load_dotenv(os.path.join(root_dir, '.env'))

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_SERVICE_KEY")

if not url or not key:
    print("Error: Missing Supabase credentials.")
    sys.exit(1)

sb = create_client(url, key)

def compare_models(days=7):
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    print(f"=== REPORTE DE RENTABILIDAD (Últimos {days} días) ===")
    
    try:
        # Fetch closed positions
        res = sb.table("positions").select("*").eq("status", "CLOSED").gte("closed_at", start_date).execute()
        positions = res.data
        
        metrics = {
            "crypto_futures": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
            "forex": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        }
        
        for p in positions:
            mtype = p.get("market_type", "")
            # agrupar crypto_spot y crypto_futures bajo la misma logica MTF
            if "crypto" in mtype:
                mtype = "crypto_futures"
            elif "forex" in mtype:
                mtype = "forex"
            else:
                continue
                
            pnl = float(p.get("pnl") or 0.0)
            
            metrics[mtype]["trades"] += 1
            metrics[mtype]["pnl"] += pnl
            if pnl > 0:
                metrics[mtype]["wins"] += 1
            elif pnl < 0:
                metrics[mtype]["losses"] += 1
                
        # Print results
        for mtype, data in metrics.items():
            winrate = (data['wins'] / data['trades'] * 100) if data['trades'] > 0 else 0
            model_name = "Crypto (Modelo Ágil MTF)" if "crypto" in mtype else "Forex (Modelo Macro DXY)"
            print(f"\n[{model_name}]")
            print(f"  - Operaciones: {data['trades']} (Wins: {data['wins']} / Losses: {data['losses']})")
            print(f"  - Win Rate:    {winrate:.1f}%")
            print(f"  - PnL Total:   ${data['pnl']:.2f}")
            
    except Exception as e:
        print(f"Error fetching data: {e}")

if __name__ == "__main__":
    compare_models(days=3) # Por defecto ultimos 3 dias
