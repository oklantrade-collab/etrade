import os

def read_log():
    log_path = r"c:\Fuentes\eTrade\backend\out.txt"
    if os.path.exists(log_path):
        with open(log_path, "rb") as f:
            content = f.read()
        # Try decoding as utf-16le
        try:
            text = content.decode("utf-16le")
            # Show last 2000 characters
            print(text[-2000:])
        except Exception as e:
            print(f"Decode error: {e}")
            # Fallback to simple read
            try:
                print(content.decode("utf-8", errors="ignore")[-2000:])
            except:
                print("Could not read log.")
    else:
        print("Log not found.")

if __name__ == "__main__":
    read_log()
