import os
import sys
import pandas as pd
import numpy as np

# Ensure backend root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.supabase_client import get_supabase

def analyze():
    sb = get_supabase()
    
    # 1. Query Crypto positions
    print("Fetching Crypto positions...")
    crypto_res = sb.table('positions').select('*').eq('status', 'closed').execute()
    crypto_df = pd.DataFrame(crypto_res.data)
    
    # 2. Query Forex positions
    print("Fetching Forex positions...")
    forex_res = sb.table('forex_positions').select('*').eq('status', 'closed').execute()
    forex_df = pd.DataFrame(forex_res.data)
    
    print(f"Loaded: {len(crypto_df)} closed Crypto positions, {len(forex_df)} closed Forex positions.\n")
    
    # Analyze Crypto SL losses
    if not crypto_df.empty:
        print("=== CRYPTO ANALYSIS ===")
        # Get stop loss reasons
        sl_positions = crypto_df[crypto_df['close_reason'].str.lower().str.contains('sl|stop', na=False)].copy()
        
        pnl_col = 'realized_pnl' # from column inspect: realized_pnl is the main non-null column
        
        print(f"Positions closed by Stop Loss: {len(sl_positions)} / {len(crypto_df)}")
        if not sl_positions.empty:
            sl_positions[pnl_col] = pd.to_numeric(sl_positions[pnl_col], errors='coerce').fillna(0)
            total_sl_loss = sl_positions[pnl_col].sum()
            
            # Let's calculate percentage changes manually for accuracy
            sl_positions['calc_pct'] = 0.0
            for idx, row in sl_positions.iterrows():
                side = str(row.get('side', 'long')).lower()
                entry = float(row.get('entry_price') or 1)
                exit_p = float(row.get('current_price') or entry)
                if entry > 0:
                    if side in ('long', 'buy'):
                        sl_positions.at[idx, 'calc_pct'] = (exit_p - entry) / entry * 100
                    else:
                        sl_positions.at[idx, 'calc_pct'] = (entry - exit_p) / entry * 100
            
            avg_sl_pct = sl_positions['calc_pct'].mean()
            
            print(f"  - Total PnL due to SL hits: ${total_sl_loss:,.2f}")
            print(f"  - Average Price change % per SL hit: {avg_sl_pct:.4f}%")
            
            # Analyze how many were small/tight wicks vs large drops
            tight_sls = sl_positions[sl_positions['calc_pct'] >= -0.50]
            print(f"  - Tight SL hits (>= -0.50% loss): {len(tight_sls)} / {len(sl_positions)} positions ({len(tight_sls)/len(sl_positions)*100:.1f}%)")
            print(f"    * Total loss of tight SLs: ${tight_sls[pnl_col].sum():,.2f}")
            print("    * These are precisely the positions EREP prevents from stopping out, by allowing them to recover.")
            
            # Print a few samples
            print("\nSamples of Crypto SL Hits:")
            for idx, r in sl_positions.head(5).iterrows():
                print(f"  * Symbol: {r.get('symbol')} | Side: {r.get('side')} | Entry: {r.get('entry_price')} | Exit: {r.get('current_price')} | Pct: {r['calc_pct']:.4f}% | PnL: ${float(r.get(pnl_col)):.4f}")

    # Analyze Forex EREP performance
    if not forex_df.empty:
        print("\n=== FOREX EREP ANALYSIS ===")
        # Column 'erep_activated_at' is sometimes null but recovery_pnl_pips or recovery_exit_reason exists, or erep_phase has been set
        # Let's filter positions that activated EREP/SLVM
        # Criteria: recovery_exit_reason is not null, or erep_activated_at is not null, or recovery_activated_at is not null
        erep_positions = forex_df[
            pd.notna(forex_df['erep_activated_at']) | 
            pd.notna(forex_df['recovery_activated_at']) | 
            pd.notna(forex_df['recovery_exit_reason']) |
            (forex_df['erep_phase'] > 0)
        ].copy()
        
        print(f"Forex positions that activated EREP/SLVM: {len(erep_positions)} / {len(forex_df)}")
        
        pnl_col_fx = 'pnl_usd'
        if pnl_col_fx in forex_df.columns:
            erep_positions[pnl_col_fx] = pd.to_numeric(erep_positions[pnl_col_fx], errors='coerce').fillna(0)
            
            # Outcome categories
            profit_pos = erep_positions[erep_positions[pnl_col_fx] > 0]
            breakeven_pos = erep_positions[(erep_positions[pnl_col_fx] >= -5.0) & (erep_positions[pnl_col_fx] <= 5.0)]
            loss_pos = erep_positions[erep_positions[pnl_col_fx] < -5.0]
            
            total_erep_pnl = erep_positions[pnl_col_fx].sum()
            recovery_rate = (len(profit_pos) + len(breakeven_pos)) / len(erep_positions) * 100 if len(erep_positions) > 0 else 0.0
            
            print(f"  - Recovered in Profit (> $0): {len(profit_pos)}")
            print(f"  - Recovered in Break-even (-$5 to +$5): {len(breakeven_pos)}")
            print(f"  - Closed in Loss (< -$5): {len(loss_pos)}")
            print(f"  - Recovery Success Rate (Profit + BE): {recovery_rate:.2f}%")
            print(f"  - Total Net PnL of EREP positions: ${total_erep_pnl:,.2f}")
            
            # Let's estimate how much would have been lost if they stopped out directly
            # Standard stop loss for forex size (e.g. 0.25 lot EURUSD is ~10-15 pips which is $25-$35 loss)
            # Let's see if we can read the initial stop loss distance: sl_price vs entry_price
            sl_losses = []
            for idx, r in erep_positions.iterrows():
                side = str(r.get('side', 'long')).lower()
                entry = float(r.get('entry_price') or 1)
                sl = float(r.get('sl_price') or entry)
                lots = float(r.get('lots') or 0.1)
                
                # Standard pips loss calculation
                pips = abs(entry - sl) * 10000 if not str(r.get('symbol')).endswith('JPY') else abs(entry - sl) * 100
                # Roughly $10 per pip per lot
                estimated_loss = pips * lots * 10.0
                sl_losses.append(-estimated_loss)
                
            assumed_sl_loss = sum(sl_losses)
            saved_loss = total_erep_pnl - assumed_sl_loss
            print(f"  - Estimated initial Stop Loss cost (if stopped immediately): ${assumed_sl_loss:,.2f}")
            print(f"  - Net profit/savings generated by EREP recovery: +${saved_loss:,.2f}")
            
            # Print a few samples
            print("\nSamples of Forex EREP/SLVM Recoveries:")
            for idx, r in erep_positions.head(5).iterrows():
                print(f"  * Symbol: {r.get('symbol')} | Side: {r.get('side')} | Entry: {r.get('entry_price')} | Exit: {r.get('recovery_exit_price') or r.get('current_price')} | Reason: {r.get('recovery_exit_reason') or r.get('close_reason')} | PnL: ${float(r.get(pnl_col_fx)):.2f}")

if __name__ == '__main__':
    analyze()
