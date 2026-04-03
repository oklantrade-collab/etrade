import os

path = r"c:\Fuentes\eTrade\backend\app\workers\scheduler.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    # Fix specifically line 1753 (index 1752) and following lines in that block
    if 1752 <= i <= 1763:
        # Check if it has the extra space (expected 37 spaces, but got 38 maybe?)
        if line.startswith(" " * 37):
             # Remove one space from the beginning
             new_lines.append(line[1:])
        else:
             new_lines.append(line)
    else:
        new_lines.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Indentation fixed.")
