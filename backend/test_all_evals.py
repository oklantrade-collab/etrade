import os
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.stocks.stocks_rule_engine import StocksRuleEngine
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, date

def evaluate_entire_watchlist():
    sb = get_supabase()
    today = date.today().isoformat()
    
    # 1. Fetch today's watchlist
    watchlist_res = sb.table('watchlist_daily')\
        .select('ticker')\
        .eq('date', today)\
        .execute()
        
    if not watchlist_res.data:
        print(f"No tickers found in watchlist_daily for {today}")
        return
        
    tickers = [r['ticker'] for r in watchlist_res.data]
    print(f"Loaded {len(tickers)} tickers for today's evaluation.")
    
    re = StocksRuleEngine.get_instance()
    
    print("\n" + "="*80)
    print(f"{'TICKER':<8} | {'PRICE':<7} | {'RVOL':<5} | {'IA_SCORE':<8} | {'TECH_SC':<7} | {'SIGNAL':<15} | {'FAIL REASON / TRIGGERED RULE'}")
    print("="*80)
    
    for ticker in tickers:
        try:
            res = sb.table('technical_scores').select('*').eq('ticker', ticker).execute()
            if not res.data:
                print(f"{ticker:<8} | N/A     | N/A   | N/A      | N/A     | N/A             | No technical scores in DB")
                continue
                
            row = res.data[0]
            signals = row.get('signals_json') or {}
            
            current_price = round(signals.get('price', 0.0), 2)
            pro_score = round(signals.get('pro_score', 0.0), 2)
            base_score = row.get('technical_score', 0.0)
            rvol = round(row.get('rvol', 1.0), 2)
            change_pct = signals.get('change_pct', 0.0)
            
            t01_confirmed = signals.get('t01_confirmed', False)
            movement_type = signals.get('movement_15m', 'lateral')
            fib_zone = signals.get('fib_zone_15m', 0)
            bb_lower = signals.get('bb_lower', 0.0)
            intrinsic_price = signals.get('composite_intrinsic', signals.get('intrinsic_price', 0.0))
            pool_type = signals.get('pool_type', 'HOT')
            sm_score = signals.get('sm_score', 1.0)
            piotroski_score = signals.get('piotroski_score', 0)
            sipv_signal = signals.get('sipv_signal', '')
            
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
            
            rule_ctx['ema_3_5m'] = signals.get('ema_3_5m', 0.0)
            rule_ctx['ema_9_5m'] = signals.get('ema_9_5m', 0.0)
            rule_ctx['ema_20_5m'] = signals.get('ema_20_5m', 0.0)
            rule_ctx['bb_expanding_5m'] = signals.get('bb_expanding_5m', False)
            rule_ctx['rsi_5m'] = signals.get('rsi_5m', 50.0)
            rule_ctx['gap_up_exhaustion'] = False
            rule_ctx['gap_pct'] = change_pct
            
            buying_results = re.evaluate_all(rule_ctx, direction="buy")
            
            triggered_rules = [res["rule_code"] for res in buying_results if res["triggered"]]
            
            if triggered_rules:
                status_desc = f"✅ BUY: {', '.join(triggered_rules)}"
            else:
                # Summarize main blockers
                blockers = []
                # Check general minimums
                if rvol < 1.0:
                    blockers.append(f"Low Vol (RVol: {rvol}x < 1.0x)")
                if pro_score < 4.0:
                    blockers.append(f"Low IA (pro_score: {pro_score} < 4.0)")
                if base_score < 30.0:
                    blockers.append(f"Low TechScore ({base_score} < 30)")
                if not blockers:
                    # Collect specific failures from S01 or BOLLINGER_EXPLOSION
                    for r in buying_results:
                        if r["rule_code"] in ["BOLLINGER_EXPLOSION", "HOT_CANDLE_BUY", "S01"]:
                            for f in r.get("failures", []):
                                if "EMA Bearish" in f or "Waterfall" in f or "BB Not Expanding" in f or "below EMA20" in f:
                                    blockers.append(f)
                
                status_desc = f"❌ Avoided: {', '.join(list(set(blockers))[:2])}"
                
            print(f"{ticker:<8} | ${current_price:<6.2f} | {rvol:<5.2f} | {pro_score:<8.2f} | {base_score:<7.1f} | {row.get('apex_signal') or 'None':<15} | {status_desc}")
        except Exception as e:
            print(f"{ticker:<8} | Error: {e}")

if __name__ == "__main__":
    evaluate_entire_watchlist()
