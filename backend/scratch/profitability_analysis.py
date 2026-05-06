import os
import pandas as pd
from app.core.supabase_client import get_supabase

def run_analysis():
    sb = get_supabase()
    
    # 1. STOCKS DATA
    stocks_res = sb.table('stocks_positions').select('*').eq('status', 'closed').execute()
    stocks_df = pd.DataFrame(stocks_res.data)
    
    # 2. FOREX DATA
    forex_res = sb.table('forex_positions').select('*').eq('status', 'closed').execute()
    forex_df = pd.DataFrame(forex_res.data)
    
    # 3. CRYPTO DATA
    crypto_res = sb.table('positions').select('*').eq('status', 'closed').execute()
    crypto_df = pd.DataFrame(crypto_res.data)
    
    print(f"Loaded: {len(stocks_df)} stocks, {len(forex_df)} forex, {len(crypto_df)} crypto")
    
    results = {}

    # --- ANALYSIS 1: 50/25/25 Value Add (Stocks Only) ---
    if not stocks_df.empty:
        # PnL columns: tp_block1_pnl, tp_block2_pnl, tp_block3_pnl
        # Fallback to pnl_usd if present
        
        stocks_df['actual_total_pnl'] = 0.0
        for col in ['tp_block1_pnl', 'tp_block2_pnl', 'tp_block3_pnl', 'pnl_usd']:
            if col in stocks_df.columns:
                stocks_df['actual_total_pnl'] += pd.to_numeric(stocks_df[col], errors='coerce').fillna(0)
        
        actual_pnl = stocks_df['actual_total_pnl'].sum()
        
        # Simulated: What if we closed 100% at Block 1? (Crypto Style - One Target)
        # We need entry_price and tp_block1_price
        entry_col = 'entry_price' if 'entry_price' in stocks_df.columns else 'avg_price'
        shares_col = 'shares' if 'shares' in stocks_df.columns else 'total_shares'
        
        if entry_col in stocks_df.columns and 'tp_block1_price' in stocks_df.columns and shares_col in stocks_df.columns:
            # We filter for rows that have tp_block1_price
            valid_stocks = stocks_df[pd.notna(stocks_df['tp_block1_price'])].copy()
            valid_stocks['sim_pnl_full_b1'] = (pd.to_numeric(valid_stocks['tp_block1_price']) - pd.to_numeric(valid_stocks[entry_col])) * pd.to_numeric(valid_stocks[shares_col])
            
            # Simulated: 2-step (50% B1, 50% B2)
            if 'tp_block2_price' in stocks_df.columns:
                valid_stocks['sim_pnl_2_step'] = (
                    (pd.to_numeric(valid_stocks['tp_block1_price']) - pd.to_numeric(valid_stocks[entry_col])) * pd.to_numeric(valid_stocks[shares_col]) * 0.5 +
                    (pd.to_numeric(valid_stocks['tp_block2_price']) - pd.to_numeric(valid_stocks[entry_col])) * pd.to_numeric(valid_stocks[shares_col]) * 0.5
                )
            else:
                valid_stocks['sim_pnl_2_step'] = valid_stocks['sim_pnl_full_b1']

            sim_pnl_b1 = valid_stocks['sim_pnl_full_b1'].sum()
            sim_pnl_2step = valid_stocks['sim_pnl_2_step'].sum()
            actual_valid_pnl = valid_stocks['actual_total_pnl'].sum()
            
            results['stocks_model_comparison'] = {
                'count': len(valid_stocks),
                'actual_50_25_25_pnl': round(actual_valid_pnl, 2),
                'sim_full_close_at_target1_pnl': round(sim_pnl_b1, 2),
                'sim_2_step_50_50_pnl': round(sim_pnl_2step, 2),
                'value_add_vs_full_pct': round(((actual_valid_pnl / sim_pnl_b1) - 1) * 100, 2) if sim_pnl_b1 != 0 else 0,
                'value_add_vs_2step_pct': round(((actual_valid_pnl / sim_pnl_2step) - 1) * 100, 2) if sim_pnl_2step != 0 else 0,
            }

    # --- ANALYSIS 2: Profitability Comparison (ROI %) ---
    
    # Stocks ROI
    if not stocks_df.empty:
        entry_col = 'entry_price' if 'entry_price' in stocks_df.columns else 'avg_price'
        shares_col = 'shares' if 'shares' in stocks_df.columns else 'total_shares'
        if entry_col in stocks_df.columns and shares_col in stocks_df.columns:
            stocks_df['roi'] = (stocks_df['actual_total_pnl'] / (pd.to_numeric(stocks_df[entry_col]) * pd.to_numeric(stocks_df[shares_col]))) * 100
            results['stocks_avg_roi_pct'] = round(stocks_df['roi'].mean(), 2)
        else:
            results['stocks_avg_roi_pct'] = 0.0

    # Forex ROI
    if not forex_df.empty:
        if 'pnl_usd' in forex_df.columns:
            forex_df['roi'] = 0.0
            for idx, row in forex_df.iterrows():
                side = str(row.get('side', 'long')).lower()
                entry = float(row.get('entry_price', 1))
                exit_p = float(row.get('current_price', entry))
                if side in ('long', 'buy'):
                    forex_df.at[idx, 'roi'] = (exit_p - entry) / entry * 100
                else:
                    forex_df.at[idx, 'roi'] = (entry - exit_p) / entry * 100
            results['forex_avg_asset_roi_pct'] = round(forex_df['roi'].mean(), 4)
        else:
            results['forex_avg_asset_roi_pct'] = 0.0

    # Crypto ROI
    if not crypto_df.empty:
        if 'pnl_pct' in crypto_df.columns:
            results['crypto_avg_roi_pct'] = round(pd.to_numeric(crypto_df['pnl_pct']).mean(), 2)
        elif 'roi_pct' in crypto_df.columns:
            results['crypto_avg_roi_pct'] = round(pd.to_numeric(crypto_df['roi_pct']).mean(), 2)
        else:
            crypto_df['roi'] = 0.0
            for idx, row in crypto_df.iterrows():
                side = str(row.get('side', 'long')).lower()
                entry = float(row.get('entry_price', 1))
                exit_p = float(row.get('current_price', entry))
                if side in ('long', 'buy'):
                    crypto_df.at[idx, 'roi'] = (exit_p - entry) / entry * 100
                else:
                    crypto_df.at[idx, 'roi'] = (entry - exit_p) / entry * 100
            results['crypto_avg_roi_pct'] = round(crypto_df['roi'].mean(), 2)

    print("--- FINAL RESULTS ---")
    import json
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    run_analysis()
