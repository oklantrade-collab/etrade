import sys
import os
sys.path.append('c:\\Fuentes\\eTrade\\backend')
from app.core.supabase_client import get_supabase
from app.stocks.stocks_rule_engine import StocksRuleEngine
import json

sb = get_supabase()
res = sb.table('technical_scores').select('*').in_('ticker', ['STEL', 'AEG', 'SOFI', 'OPEN', 'WEN', 'NU']).execute()
re = StocksRuleEngine.get_instance()
output = {}

for r in res.data:
    t = r['ticker']
    snap = r.get('signals_json', {})
    ctx = re.build_context(t, snap, pine_signal=snap.get('last_pinescript_signal', ''), rvol=snap.get('rvol', 1.0), fundamental_score=snap.get('fundamental_score',0), bb_expanding=snap.get('bb_expanding', False))
    res_buy = re.evaluate_all(ctx, direction='buy')
    output[t] = [{'rule': x['rule_code'], 'triggered': x['triggered'], 'failures': x['failures']} for x in res_buy]

print(json.dumps(output, indent=2))
