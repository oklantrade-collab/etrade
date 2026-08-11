import sys
import os
from dotenv import load_dotenv
load_dotenv('c:/Fuentes/eTrade/backend/.env')
from binance.client import Client

def check_pos():
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    client = Client(api_key, api_secret)
    
    positions = client.futures_position_information(symbol="ADAUSDT")
    print("=== BINANCE FUTURES POSITIONS FOR ADAUSDT ===")
    for p in positions:
        amt = float(p.get('positionAmt', 0))
        if amt != 0 or p.get('positionSide') == 'LONG':
            print(f"Symbol: {p['symbol']} | Side: {p['positionSide']} | Amt: {p['positionAmt']} | EntryPx: ${p['entryPrice']} | UnPnl: ${p['unRealizedProfit']}")

if __name__ == "__main__":
    check_pos()
