with open('c:/Fuentes/eTrade/frontend/app/forex/positions/page.tsx', 'r', encoding='utf-8') as f:
    content = f.read()

import re
numbers = re.findall(r'\b\d+\b', content)
print("Numeric values in file:", set(numbers))
