import os

filepath = r'c:\Fuentes\eTrade\backend\app\workers\scheduler.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if 'from app.strategy.strategy_engine import StrategyEngine' in line and 'import asyncio' not in line and line.strip().startswith('from'):
        # Check if it's the one at the top (global) or inside a function
        # The global one is at the beginning of the file, indentation 0.
        if line.startswith('from'):
             # If it starts with 'from' (no spaces), keep it
             new_lines.append(line)
        else:
             # If it has spaces (indented), skip it (redundant local import)
             continue
    else:
        new_lines.append(line)

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Redundant local StrategyEngine imports removed.")
