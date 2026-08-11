import sys
import os
import asyncio
from dotenv import load_dotenv

load_dotenv('c:/Fuentes/eTrade/backend/.env')
sys.path.append('c:/Fuentes/eTrade/backend')

from app.core.supabase_client import get_supabase
from binance.client import Client
from binance.exceptions import BinanceAPIException

async def test_and_trade():
    print("="*60)
    print("1. VERIFICANDO CONEXION A BINANCE FUTURES API...")
    print("="*60)
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    print(f"   API Key: {api_key[:8]}...{api_key[-6:] if api_key else ''}")

    client = Client(api_key, api_secret)
    sb = get_supabase()
    
    try:
        account = client.futures_account()
        total_balance = account.get('totalWalletBalance', '0')
        available_balance = account.get('availableBalance', '0')
        print(f"[OK] CONEXION Y ACCESO IP CORRECTOS EN BINANCE FUTURES!")
        print(f"   Saldo Total Wallet USDT: ${float(total_balance):.2f}")
        print(f"   Saldo Disponible USDT: ${float(available_balance):.2f}")
    except BinanceAPIException as e:
        print(f"[ERROR] ERROR DE BINANCE API ({e.code}): {e.message}")
        return
    except Exception as e:
        print(f"[ERROR] ERROR INESPERADO CONECTANDO A BINANCE: {e}")
        return

    print("\n2. EJECUTANDO ORDEN REAL DE PRUEBA: ADAUSDT LONG (MARKET)...")
    symbol = "ADAUSDT"
    
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        
        # Quantity 35 ADA = ~$6.90 USDT (Mínimo notional Binance = $5.00)
        qty = 35.0
        notional = qty * current_price
        
        print(f"   Precio actual de {symbol}: ${current_price:.4f}")
        print(f"   Cantidad a comprar: {qty} ADA (~${notional:.2f} USDT)")
        
        # Ajustar apalancamiento a 5x
        try:
            client.futures_change_leverage(symbol=symbol, leverage=5)
            print("   Apalancamiento ajustado a 5x.")
        except Exception as lev_e:
            print(f"   Aviso apalancamiento: {lev_e}")

        # Ejecutar Orden Real en Binance Futures
        order = client.futures_create_order(
            symbol=symbol,
            side='BUY',
            positionSide='LONG',
            type='MARKET',
            quantity=qty
        )
        
        print(f"\n[OK] ¡ORDEN EN REAL EJECUTADA EXITOSAMENTE EN BINANCE FUTURES!")
        print(f"   Binance Order ID: {order.get('orderId')}")
        print(f"   Symbol: {order.get('symbol')}")
        print(f"   Side: {order.get('side')} / PositionSide: {order.get('positionSide')}")
        print(f"   Executed Qty: {order.get('executedQty')} ADA")
        print(f"   Avg Price: ${order.get('avgPrice', current_price)}")
        print(f"   Status: {order.get('status')}")

        # Registrar orden en Supabase
        try:
            sb.table('orders').insert({
                'symbol': 'ADAUSDT',
                'side': 'BUY',
                'order_type': 'MARKET',
                'quantity': qty,
                'status': 'filled',
                'is_paper': False,
                'binance_order_id': str(order.get('orderId'))
            }).execute()
            print("   [OK] Orden real registrada en tabla orders de Supabase (is_paper=False).")
        except Exception as db_e:
            print(f"   [AVISO] No se pudo insertar en orders: {db_e}")
        
    except BinanceAPIException as e:
        print(f"\n[ERROR] ERROR DE BINANCE AL CREAR LA ORDEN ({e.code}): {e.message}")
    except Exception as e:
        print(f"\n[ERROR] ERROR INESPERADO AL CREAR ORDEN: {e}")

if __name__ == "__main__":
    asyncio.run(test_and_trade())
