import os
import sys

def read_logs():
    p = 'forex_debug.log'
    if not os.path.exists(p):
        print(f"Log file {p} does not exist")
        return
    with open(p, 'rb') as f:
        data = f.read()
    
    # Try UTF-16
    try:
        content = data.decode('utf-16')
        print("Decoded as UTF-16:")
    except Exception:
        try:
            content = data.decode('utf-8', errors='ignore')
            print("Decoded as UTF-8:")
        except Exception as e:
            print("Failed to decode:", e)
            return
            
    lines = content.splitlines()
    print(f"Total lines: {len(lines)}")
    print("--- Last 50 lines ---")
    for line in lines[-50:]:
        print(line)

    print("\n--- Search for 'vinculados' or 'symbol' in first 200 lines on startup ---")
    for line in lines[:200]:
        if any(w in line.lower() for w in ['vinculados', 'symbol', 'error', 'warning', 'id']):
            print(line)

if __name__ == "__main__":
    read_logs()
