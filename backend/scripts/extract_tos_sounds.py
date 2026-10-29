import os
import zipfile

tos_path = r"C:\Users\jyups\AppData\Local\thinkorswim"
output_dir = r"c:\Fuentes\eTrade\backend\scripts\tos_sounds"
os.makedirs(output_dir, exist_ok=True)

found_jar = None
for root, dirs, files in os.walk(tos_path):
    for f in files:
        if f.startswith("tos-usergui-base") and f.endswith(".jar"):
            found_jar = os.path.join(root, f)
            print(f"Found JAR: {found_jar}")
            with zipfile.ZipFile(found_jar, 'r') as z:
                for n in z.namelist():
                    if n.startswith("com/devexperts/tos/widgets/sounds/"):
                        filename = os.path.basename(n)
                        if filename:
                            out_path = os.path.join(output_dir, filename)
                            with open(out_path, "wb") as out_f:
                                out_f.write(z.read(n))
                            print(f"Extracted: {filename} ({os.path.getsize(out_path)} bytes)")

print("Extraction complete!")
