import os

path = r"c:\Fuentes\eTrade\backend\app\workers\scheduler.py"
with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for i, line in enumerate(lines):
    # Fix from 1753 (index 1752) up to 1779 (index 1778)
    if 1752 <= i <= 1778:
        # Check if it has the problematic leading spaces
        # Line 1752 (index 1751) had: "                                    signal_4h" (36 spaces)
        # Line 1753 (index 1752) had: "                                     if signal_4h:" (37 spaces)
        # All lines from 1753 to 1779 seem to have 1 extra space
        if line.startswith(" "):
             new_lines.append(line[1:])
        else:
             new_lines.append(line)
    else:
        new_lines.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Indentation corrected.")
