import requests

try:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    res = requests.get("https://etrade-flame.vercel.app/forex/positions", headers=headers)
    print(f"Status: {res.status_code}")
    print(f"HTML Length: {len(res.text)}")
    # Find any page numbers in the HTML
    import re
    buttons = re.findall(r'<button[^>]*>(\d+)</button>', res.text)
    print("Page buttons in HTML:", buttons)
except Exception as e:
    print(f"Error: {e}")
