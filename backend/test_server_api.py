import subprocess

def run_ssh_command(cmd_str):
    ssh_cmd = [
        "ssh", "-i", "C:/Users/jyups/.ssh/etrade_cloud_key",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "root@207.154.224.71",
        cmd_str
    ]
    res = subprocess.run(ssh_cmd, capture_output=True, text=True)
    return res.stdout, res.stderr

print("--- Searching all logs for 'Project not specified' ---")
stdout, stderr = run_ssh_command("journalctl -u etrade-api --grep='Project not specified' --no-pager")
print(stdout)
if stderr:
    print("ERR:", stderr)
