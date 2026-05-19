with open('c:/Fuentes/eTrade/frontend/app/forex/positions/page.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for idx, line in enumerate(lines):
    if 'closed' in line.lower() or 'page' in line.lower():
        print(f"{idx+1}: {line.strip()}")
