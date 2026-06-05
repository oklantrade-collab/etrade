import os

log_path = r"C:\Users\jyups\.pm2\logs\etrade-forex-out.log"

def safe_print(msg):
    try:
        print(msg.encode('ascii', 'ignore').decode('ascii'))
    except:
        pass

def search_log():
    if not os.path.exists(log_path):
        safe_print(f"Log path does not exist: {log_path}")
        return
        
    safe_print(f"Searching log file: {log_path}")
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
        
    safe_print("=== Last 100 lines ===")
    for line in lines[-100:]:
        safe_print(line.strip())
        
    safe_print("=== Symbol bindings in log ===")
    for line in lines:
        if "vinculados" in line or "symbol_ids" in line or "prices" in line:
            safe_print(line.strip())

if __name__ == "__main__":
    search_log()
