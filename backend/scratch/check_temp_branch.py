import subprocess

try:
    res = subprocess.run(["git", "show", "origin/temp-branch:frontend/app/forex/positions/page.tsx"], capture_output=True, check=True)
    content = res.stdout.decode('utf-8')
    for idx, line in enumerate(content.split('\n')):
        if "useState" in line:
            print(f"{idx+1}: {line}")
except Exception as e:
    print(f"Error: {e}")
