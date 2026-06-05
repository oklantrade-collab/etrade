import os

log_dir = r"C:\Users\jyups\.pm2\logs"

def search_log():
    if not os.path.exists(log_dir):
        print(f"Log directory does not exist: {log_dir}")
        return
        
    targets = ['1.16481', 'd5807bc5', '1.34559']
    
    for filename in os.listdir(log_dir):
        file_path = os.path.join(log_dir, filename)
        if os.path.isfile(file_path):
            print(f"Searching log file: {file_path}")
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    for target in targets:
                        if target in line:
                            print(f"[{filename}] {line.strip()}")
                            break

if __name__ == "__main__":
    search_log()
