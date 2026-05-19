with open('c:/Fuentes/eTrade/frontend/app/forex/positions/page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

lines = content.split('\n')
for idx, line in enumerate(lines[:150]):
    print(f"{idx+1}: {line}")
