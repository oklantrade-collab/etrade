import traceback
from app.core.supabase_client import get_supabase
from datetime import datetime, timezone

def test_insert():
    sb = get_supabase()
    indicators = {"rsi_14": 50, "close": 10}
    pro_score = 12.3
    technical_score = 40
    fib_level = "middle_zone"
    mtf_confirmed = True
    macd_signal_dir = "bullish"
    ticker = "TESTDUMMY2"
    
    row = {
        "ticker":            ticker,
        "timestamp":         datetime.now(timezone.utc).isoformat(),
        "rsi_14":            indicators.get("rsi_14"),
        "atr_14":            indicators.get("atr_14"),
        "bollinger_squeeze": indicators.get("bb_squeeze", False),
        "macd_signal":       macd_signal_dir,
        "ema_alignment":     indicators.get("ema_alignment", "unknown"),
        "rvol":              indicators.get("rvol"),
        "fib_level":         fib_level,
        "mtf_confirmed":     mtf_confirmed,
        "technical_score":   technical_score,
        "signals_json":      {
            "price": indicators.get("close"),
            "volume": indicators.get("volume"),
            "rsi": indicators.get("rsi_14"),
            "adx": indicators.get("adx_14"),
            "macd_hist": indicators.get("macd_histogram"),
            "stoch_k": indicators.get("stoch_k"),
            "di_plus": indicators.get("di_plus"),
            "di_minus": indicators.get("di_minus"),
            "change_pct": indicators.get("change_pct", 0.0),
            "market_cap": indicators.get("market_cap", 0),
            "rvol": indicators.get("rvol", 1.0),
            "volume": indicators.get("volume", 0),
            "pro_score": pro_score,
            "ai_rationale": indicators.get("ai_rationale", ""),
            "qwen_score": indicators.get("qwen_score", 0),
            "gemini_score": indicators.get("gemini_score", 0),
            "qwen_summary": indicators.get("qwen_summary", ""),
            "gemini_summary": indicators.get("gemini_summary", ""),
            "intrinsic_value": indicators.get("intrinsic_value", 0),
            "undervaluation": indicators.get("undervaluation", 0),
            # Smart Limit & Movement (Multi-TF)
            "movement_15m": indicators.get("movement_15m"),
            "fib_zone_15m": indicators.get("fib_zone_15m"),
            "limit_long_15m": indicators.get("limit_long_15m"),
            "limit_short_15m": indicators.get("limit_short_15m"),
            "movement_1d": indicators.get("movement_1d"),
            "fib_zone_1d": indicators.get("fib_zone_1d"),
            "limit_long_1d": indicators.get("limit_long_1d"),
            "limit_short_1d": indicators.get("limit_short_1d"),
            "t01_confirmed": indicators.get("t01_confirmed", False),
            "t02_confirmed": indicators.get("t02_confirmed", False),
            "t03_confirmed": indicators.get("t03_confirmed", False),
            "t04_confirmed": indicators.get("t04_confirmed", False),
            "limit_long_1m": indicators.get("limit_long_1m"),
            "limit_short_1m": indicators.get("limit_short_1m"),
            "smart_limit_long_15m": indicators.get("smart_limit_long_15m"),
            "smart_limit_short_15m": indicators.get("smart_limit_short_15m"),
            "smart_limit_long_1d": indicators.get("smart_limit_long_1d"),
            "smart_limit_short_1d": indicators.get("smart_limit_short_1d")
        }
    }
    
    try:
        sb.table('technical_scores').insert(row).execute()
        print('INSERT ROW EXACT SUCCESS')
    except Exception as e:
        print(f"INSERT ROW EXACT ERROR: {e}")
        print(traceback.format_exc())

if __name__ == "__main__":
    test_insert()
