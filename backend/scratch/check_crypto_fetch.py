with open('c:/Fuentes/eTrade/frontend/app/positions/page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

for idx, line in enumerate(content.split('\n')):
    if "setClosedPositions" in line or "fetch" in line:
        print(f"{idx+1}: {line}")
