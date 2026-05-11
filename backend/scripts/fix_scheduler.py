import os

file_path = r'c:\Fuentes\eTrade\backend\app\workers\scheduler.py'
with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if 'engine = StrategyEngine.get_instance()' in line and 'if BOT_STATE.config_cache.get(\'use_strategy_engine_v2\'):' in lines[lines.index(line)-1]:
        indent = line[:line.find('engine')]
        new_lines.append(line)
        new_lines.append(f'{indent}sm.sync_single_symbol(symbol)\n')
    else:
        new_lines.append(line)

with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("Applied sync_single_symbol to StrategyEngine blocks")
