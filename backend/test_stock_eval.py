import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.stocks.stocks_rule_engine import StocksRuleEngine
from zoneinfo import ZoneInfo
from datetime import datetime, timezone

def test_eval(ticker):
    print(f"\n==========================================")
    print(f"EVALUATING TICKER: {ticker}")
    print(f"==========================================")
    
    sb = get_supabase()
    
    # 1. Fetch technical score row
    res = sb.table('technical_scores').select('*').eq('ticker', ticker).execute()
    if not res.data:
        print(f"No technical scores found for {ticker}")
        return
        
    row = res.data[0]
    signals = row.get('signals_json') or {}
    
    # 2. Build context similar to stocks_scheduler.py
    re = StocksRuleEngine.get_instance()
    
    # Extract values
    current_price = signals.get('price', 0.0)
    pro_score = signals.get('pro_score', 0.0)
    base_score = row.get('technical_score', 0.0)
    rvol = row.get('rvol', 1.0)
    change_pct = signals.get('change_pct', 0.0)
    
    t01_confirmed = signals.get('t01_confirmed', False)
    t02_confirmed = signals.get('t02_confirmed', False)
    t03_confirmed = signals.get('t03_confirmed', False)
    
    movement_type = signals.get('movement_15m', 'lateral')
    fib_zone = signals.get('fib_zone_15m', 0)
    bb_lower = signals.get('bb_lower', 0.0)
    intrinsic_price = signals.get('composite_intrinsic', signals.get('intrinsic_price', 0.0))
    pool_type = signals.get('pool_type', 'HOT')
    sm_score = signals.get('sm_score', 1.0)
    piotroski_score = signals.get('piotroski_score', 0)
    sipv_signal = signals.get('sipv_signal', '')
    
    print(f"Price: ${current_price:.2f} | Chg%: {change_pct:+.2f}% | RVol: {rvol:.2f}")
    print(f"IA Score (pro_score): {pro_score:.2f} | TechScore: {base_score:.1f}")
    print(f"T01(Pine): {t01_confirmed} | T02(EMA): {t02_confirmed} | T03(Vela): {t03_confirmed}")
    print(f"Movement: {movement_type} | FibZone: {fib_zone} | Pool: {pool_type}")
    print(f"SM Score: {sm_score} | Piotroski: {piotroski_score} | SIPV Signal: {sipv_signal}")
    print(f"Apex Signal: {row.get('apex_signal')} | Apex4H: {row.get('apex_4h')} | Apex1D: {row.get('apex_1d')}")
    
    rule_ctx = re.build_context(
        ticker=ticker,
        snap=signals,
        ia_score=pro_score,
        tech_score=base_score,
        fundamental_score=signals.get("fundamental_score", 0),
        rvol=rvol,
        pine_signal="Buy" if t01_confirmed else "",
        movement_type=movement_type,
        fib_zone=fib_zone,
        bb_lower=bb_lower,
        intrinsic_price=intrinsic_price,
        pool_type=pool_type,
        sm_score=sm_score,
        piotroski_score=piotroski_score,
        sipv_signal=sipv_signal,
        ema_3=signals.get("ema_3"),
        ema_9=signals.get("ema_9"),
        ema_20=signals.get("ema_20"),
        bb_expanding=signals.get("bb_expanding", False),
        ema_exhaustion=signals.get("ema_exhaustion", False),
        ema3_cross_age=signals.get("ema3_cross_ema9_age", 999)
    )
    
    # Add 5m values
    rule_ctx['ema_3_5m'] = signals.get('ema_3_5m', 0.0)
    rule_ctx['ema_9_5m'] = signals.get('ema_9_5m', 0.0)
    rule_ctx['ema_20_5m'] = signals.get('ema_20_5m', 0.0)
    rule_ctx['bb_expanding_5m'] = signals.get('bb_expanding_5m', False)
    rule_ctx['rsi_5m'] = signals.get('rsi_5m', 50.0)
    
    gap_up_exhaustion = False
    try:
        now_et = datetime.now(timezone.utc).astimezone(ZoneInfo('America/New_York'))
        hours_since_open = (now_et.hour - 9) + (now_et.minute - 30) / 60.0
        if change_pct > 3.0 and hours_since_open > 2.0:
            gap_up_exhaustion = True
    except:
        pass
    rule_ctx['gap_up_exhaustion'] = gap_up_exhaustion
    rule_ctx['gap_pct'] = change_pct
    
    if t01_confirmed:
        rule_ctx["pine_signal"] = "Buy"
    
    # 3. Evaluate Buy Rules
    print("\n--- BUY RULES EVALUATION ---")
    buying_results = re.evaluate_all(rule_ctx, direction="buy")
    triggered_any = False
    for res in buying_results:
        code = res["rule_code"]
        if res["triggered"]:
            triggered_any = True
            print(f"[✅ TRIGGERED] Rule: {code} | Order Type: {res['order_type']} | Price: {res['order_price']}")
        else:
            print(f"[❌ FAILED] Rule: {code}")
            for f in res.get("failures", []):
                print(f"   - {f}")
                
    if not triggered_any:
        print("\nResult: No BUY rules triggered.")
    else:
        print("\nResult: At least one BUY rule triggered!")

if __name__ == "__main__":
    # If tickers are passed via command line, evaluate them, otherwise evaluate top ones
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["SOC", "BMNR", "RXRX", "BB", "TE", "JBLU"]
    for t in tickers:
        try:
            test_eval(t)
        except Exception as ex:
            print(f"Error evaluating {t}: {ex}")

