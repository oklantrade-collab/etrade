import subprocess

try:
    res = subprocess.run(["git", "log", "--all", "-S", "useState(16)", "--oneline"], capture_output=True, text=True, check=True)
    print("Commits with useState(16):", res.stdout)
except Exception as e:
    print(f"Error: {e}")
