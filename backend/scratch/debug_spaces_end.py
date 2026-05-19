with open('c:/Fuentes/eTrade/frontend/app/forex/positions/page.tsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i in range(418, 427):
    print(f"{i+1}: {repr(lines[i])}")
