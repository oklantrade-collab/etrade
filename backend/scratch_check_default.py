from app.core.supabase_client import get_supabase

def run():
    sb = get_supabase()
    # Insert a dummy position
    try:
        res = sb.table('positions').insert({
            'symbol': 'TESTUSDT',
            'side': 'LONG',
            'entry_price': 1.0,
            'size': 1.0,
            'status': 'open',
            'rule_code': 'TEST',
            'mode': 'paper'
        }).execute()
        if res.data:
            pos = res.data[0]
            print("TEST POSITION INSERTED SUCCESSFULLY!")
            print(f"erep_active: {pos.get('erep_active')}")
            print(f"erep_phase: {pos.get('erep_phase')}")
            print(f"erep_cycles_elapsed: {pos.get('erep_cycles_elapsed')}")
            
            # Clean up
            sb.table('positions').delete().eq('id', pos['id']).execute()
            print("TEST POSITION CLEANED UP.")
    except Exception as e:
        print("Error inserting test position:", e)

if __name__ == '__main__':
    run()
