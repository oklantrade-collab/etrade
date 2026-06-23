with open('c:/Fuentes/eTrade/backend/app/core/position_monitor.py', 'r', encoding='utf-8') as f:
    content = f.read()

target = "'sl_type': f'trailing_l{trail[\"new_level\"]}',"
replacement = "'sl_type': trail.get('sl_type', f'trailing_l{trail[\"new_level\"]}'),"

content = content.replace(target, replacement)

with open('c:/Fuentes/eTrade/backend/app/core/position_monitor.py', 'w', encoding='utf-8') as f:
    f.write(content)
