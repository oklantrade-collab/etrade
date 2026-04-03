import os
import asyncio
from app.core.supabase_client import get_supabase

async def verify_hierarchy():
    sb = get_supabase()
    res = sb.table('market_snapshot').select('*').eq('symbol', 'BTCUSDT').execute()
    if not res.data:
        print("No hay datos")
        return
    r = res.data[0]
    
    levels = [
        ('lower_6', r['lower_6']),
        ('lower_5', r['lower_5']),
        ('lower_4', r['lower_4']),
        ('lower_3', r['lower_3']),
        ('lower_2', r['lower_2']),
        ('lower_1', r['lower_1']),
        ('basis',   r['basis']),
        ('upper_1', r['upper_1']),
        ('upper_2', r['upper_2']),
        ('upper_3', r['upper_3']),
        ('upper_4', r['upper_4']),
        ('upper_5', r['upper_5']),
        ('upper_6', r['upper_6'])
    ]
    
    print("\nVALORES EN SUPABASE:")
    for name, val in levels:
        print(f"  {name:10}: {val}")
    
    # Check hierarchy
    is_correct = True
    for i in range(len(levels)-1):
        if not (levels[i][1] < levels[i+1][1]):
            is_correct = False
            print(f"  [ERROR] {levels[i][0]} ({levels[i][1]}) >= {levels[i+1][0]} ({levels[i+1][1]})")
            
    print(f"\nJERARQUIA CORRECTA: {is_correct}")

if __name__ == "__main__":
    asyncio.run(verify_hierarchy())
