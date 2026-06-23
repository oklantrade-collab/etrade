import subprocess
import os

SERVER_IP = "165.22.87.171"
SSH_KEY = "C:/Users/jyups/.ssh/etrade_cloud_key"
REMOTE_PATH = "/home/etrade/etrade/backend"

files_to_sync = [
    "app/workers/scheduler.py",
    "app/workers/forex_scheduler.py"
]

def check_syntax():
    import py_compile
    print("=" * 60)
    print("Preventive syntax check...")
    print("=" * 60)
    all_ok = True
    for f in files_to_sync:
        local_file = os.path.join("c:/Fuentes/eTrade/backend", f)
        try:
            py_compile.compile(local_file, doraise=True)
            print(f"[OK] {f}")
        except py_compile.PyCompileError as e:
            print(f"[FAIL] SYNTAX ERROR IN: {f}")
            print(str(e))
            all_ok = False
        except FileNotFoundError:
            print(f"[WARN] File not found: {f}")
            
    if not all_ok:
        print("\n[CRITICAL] Deployment aborted due to syntax errors.")
        return False
    return True

def deploy():
    if not check_syntax():
        return
        
    for f in files_to_sync:
        local_file = os.path.join("c:/Fuentes/eTrade/backend", f)
        remote_file = f"root@{SERVER_IP}:{REMOTE_PATH}/{f}"
        
        print(f"Deploying {f}...")
        cmd = [
            "scp", "-i", SSH_KEY,
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            local_file, remote_file
        ]
        subprocess.run(cmd, check=True)

    print("\nRestarting services on the remote server...")
    restart_cmd = [
        "ssh", "-i", SSH_KEY, 
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{SERVER_IP}",
        "systemctl restart etrade-crypto etrade-forex etrade-forex-scheduler etrade-api etrade-stocks"
    ]
    subprocess.run(restart_cmd, check=True)
    print("Fast deployment and services restart completed successfully!")

if __name__ == "__main__":
    deploy()
