
import os
import sys
import time
from datetime import datetime, timezone
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.supabase_client import get_supabase
from app.core.logger import log_info, log_error

def verify_optimizations():
    sb = get_supabase()
    
    def get_log_count():
        res = sb.table("system_logs").select("id", count="exact").limit(1).execute()
        return res.count or 0

    print("--- OPTIMIZATION VERIFICATION ---")
    initial_count = get_log_count()
    print(f"Initial log count: {initial_count}")

    # Test INFO log (should NOT be in DB)
    test_msg_info = f"VERIFICATION_TEST_INFO_{int(time.time())}"
    print(f"Sending INFO log: {test_msg_info}")
    log_info("VERIFIER", test_msg_info)
    
    time.sleep(2) # Give it a moment
    count_after_info = get_log_count()
    print(f"Count after INFO: {count_after_info}")
    
    if count_after_info == initial_count:
        print("✅ SUCCESS: INFO log was NOT written to DB.")
    else:
        print("❌ FAILURE: INFO log was written to DB.")

    # Test ERROR log (should BE in DB)
    test_msg_err = f"VERIFICATION_TEST_ERROR_{int(time.time())}"
    print(f"Sending ERROR log: {test_msg_err}")
    log_error("VERIFIER", test_msg_err)
    
    time.sleep(2)
    count_after_err = get_log_count()
    print(f"Count after ERROR: {count_after_err}")
    
    if count_after_err > count_after_info:
        print("✅ SUCCESS: ERROR log was written to DB (Persistence working for critical levels).")
    else:
        print("❌ FAILURE: ERROR log was NOT written to DB.")

    # Cleanup test error from DB to keep it clean
    sb.table("system_logs").delete().eq("message", test_msg_err).execute()
    print("Cleaned up test error.")

if __name__ == "__main__":
    verify_optimizations()
