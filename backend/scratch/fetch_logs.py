import subprocess

SERVER_IP = "165.22.87.171"
SSH_KEY = "C:/Users/jyups/.ssh/etrade_cloud_key"

try:
    cmd = [
        "ssh", "-i", SSH_KEY, 
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"root@{SERVER_IP}",
        "journalctl -u etrade-crypto -n 100 --no-pager"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    with open("remote_logs.txt", "w", encoding="utf-8") as f:
        f.write(result.stdout)
        f.write("\n--- STDERR ---\n")
        f.write(result.stderr)
    print("Logs guardados en remote_logs.txt")
except Exception as e:
    print(f"Error fetching logs: {e}")
