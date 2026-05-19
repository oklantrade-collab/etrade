import subprocess

try:
    res = subprocess.run(["git", "log", "--all", "-S", "useState(17)", "--oneline"], capture_output=True, text=True, check=True)
    print("Commits with useState(17):", res.stdout)
except Exception as e:
    print(f"Error: {e}")
