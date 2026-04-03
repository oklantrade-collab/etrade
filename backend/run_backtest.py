"""
Script para ejecutar el backtesting manualmente - SPRINT 2.
Corregido encoding para Windows y diagnostico.
"""
import asyncio
import os
import sys
import traceback

# Ensure backend is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["PYTHONIOENCODING"] = "utf-8"

from app.backtesting.backtester import run_backtest, save_backtest_to_supabase
from app.strategy.rule_engine import DEFAULT_RULES

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'ADAUSDT']
TIMEFRAMES = ["15m"]
LIMIT = 2500


async def main():
    print("\n" + "=" * 60)
    print("  eTrade Sprint 2 - Backtester (Dia 2)")
    print(f"  Symbols: {SYMBOLS}")
    print(f"  Timeframes: {TIMEFRAMES}")
    print(f"  Limit: {LIMIT} velas")
    print("=" * 60)

    # Diagnostico: Reglas cargadas
    rule_codes = [r["rule_code"] for r in DEFAULT_RULES]
    print(f"\n[DIAGNOSTICO] Reglas cargadas ({len(rule_codes)}): {rule_codes}")

    all_results = []

    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            print(f"\n{'=' * 50}")
            print(f"  Backtesting {symbol} {tf}...")
            print(f"{'=' * 50}")

            try:
                results = await run_backtest(
                    symbol=symbol,
                    timeframe=tf,
                    limit=LIMIT,
                )
            except Exception as e:
                print(f"\n  EXCEPCION EN {symbol}:")
                traceback.print_exc()
                continue

            if "error" in results:
                print(f"  ERROR: {results['error']}")
                continue

            # --- DIAGNOSTICO DE REGLAS (BUG 3) ---
            print('\n=== DIAGNOSTICO DE CONDICIONES POR REGLA ===')
            triggered = results.get('rules_triggered', {})
            for rc in ['Aa11','Aa12','Aa13','Aa21','Aa22','Aa23','Aa24',
                       'Bb11','Bb12','Bb13','Bb21','Bb22','Bb23']:
                count = triggered.get(rc, 0)
                status = "OK" if count > 0 else "NO"
                print(f"  {rc}: {count:>3} trades | status={status}")

            print(f"\n  --- Resultados {symbol} ---")
            print(f"  Total trades:      {results['total_trades']}")
            print(f"  Winning trades:    {results['winning_trades']}")
            print(f"  Losing trades:     {results['losing_trades']}")
            print(f"  Win rate:          {results['win_rate_pct']}%")
            print(f"  P&L total:         ${results['total_pnl_usd']}")
            print(f"  RR promedio:       {results['avg_rr_real']}")
            
            # Save to Supabase
            print(f"\n  Guardando en Supabase...")
            saved = await save_backtest_to_supabase(results)
            if saved:
                print(f"  [OK] Guardado en Supabase")
            else:
                print(f"  [FAIL] Error guardando en Supabase")

            all_results.append(results)

    print(f"\n{'=' * 60}")
    print(f"  RESUMEN FINAL COMBINADO")
    print(f"{'=' * 60}")
    total_trades = sum(r.get("total_trades", 0) for r in all_results)
    total_pnl = sum(r.get("total_pnl_usd", 0) for r in all_results)
    print(f"  Total trades: {total_trades}")
    print(f"  P&L total:    ${total_pnl:.2f}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
