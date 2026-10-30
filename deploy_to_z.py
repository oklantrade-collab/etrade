import os
import shutil
import filecmp

source_base = "C:/Fuentes/eTrade"
target_base = "Z:/etrade"

# Core folders and specific files to sync to APOLO
folders_to_sync = [
    "backend/app/options",
    "backend/app/core",
    "backend/app/stocks",
    "backend/app/workers",
    "backend/app/data",
    "backend/app/api",
]

individual_files = [
    "run_ib_bridge.bat",
    "backend/run_options_worker.bat",
    "backend/app/main.py",
]

def sync_to_apolo():
    if not os.path.exists(target_base):
        print(f"❌ ERROR: {target_base} no está accesible. Verifique la conexión de red a APOLO (\\192.168.1.105\\Fuentes).")
        return False

    print(f"============================================================")
    print(f"   SINCRONIZANDO ETRADE HACIA SERVIDOR APOLO ({target_base})")
    print(f"============================================================")

    copied_files = []
    skipped_files = []
    error_files = []

    # 1. Sync folders
    for folder in folders_to_sync:
        src_dir = os.path.join(source_base, folder.replace("/", os.sep))
        dst_dir = os.path.join(target_base, folder.replace("/", os.sep))

        if not os.path.exists(src_dir):
            continue

        for root, dirs, files in os.walk(src_dir):
            if any(x in root for x in ["__pycache__", ".pytest_cache"]):
                continue
            rel_path = os.path.relpath(root, src_dir)
            target_sub_dir = os.path.join(dst_dir, rel_path) if rel_path != "." else dst_dir

            for f in files:
                if f.endswith((".pyc", ".tmp", ".log")):
                    continue
                src_file = os.path.join(root, f)
                dst_file = os.path.join(target_sub_dir, f)
                display_name = os.path.relpath(src_file, source_base)

                needs_copy = False
                if not os.path.exists(dst_file):
                    needs_copy = True
                else:
                    if not filecmp.cmp(src_file, dst_file, shallow=False):
                        needs_copy = True

                if needs_copy:
                    try:
                        os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                        shutil.copy2(src_file, dst_file)
                        size_kb = os.path.getsize(src_file) / 1024
                        print(f"  [COPIADO] {display_name} ({size_kb:.1f} KB)")
                        copied_files.append(display_name)
                    except Exception as e:
                        print(f"  [ERROR] {display_name}: {e}")
                        error_files.append((display_name, str(e)))
                else:
                    skipped_files.append(display_name)

    # 2. Sync individual files
    for item in individual_files:
        src_file = os.path.join(source_base, item.replace("/", os.sep))
        dst_file = os.path.join(target_base, item.replace("/", os.sep))

        if not os.path.exists(src_file):
            continue

        needs_copy = False
        if not os.path.exists(dst_file):
            needs_copy = True
        else:
            if not filecmp.cmp(src_file, dst_file, shallow=False):
                needs_copy = True

        if needs_copy:
            try:
                os.makedirs(os.path.dirname(dst_file), exist_ok=True)
                shutil.copy2(src_file, dst_file)
                size_kb = os.path.getsize(src_file) / 1024
                print(f"  [COPIADO] {item} ({size_kb:.1f} KB)")
                copied_files.append(item)
            except Exception as e:
                print(f"  [ERROR] {item}: {e}")
                error_files.append((item, str(e)))
        else:
            skipped_files.append(item)

    print(f"\n============================================================")
    print(f"   RESUMEN DE SINCRONIZACIÓN A SERVIDOR APOLO")
    print(f"============================================================")
    print(f"Archivos actualizados/copiados : {len(copied_files)}")
    print(f"Archivos ya idénticos (al día) : {len(skipped_files)}")
    print(f"Errores de copiado            : {len(error_files)}")
    if copied_files:
        print("\nDetalle de archivos sincronizados a APOLO:")
        for cf in copied_files:
            print(f"  ✓ {cf}")
    print(f"============================================================\n")
    return len(error_files) == 0

if __name__ == "__main__":
    sync_to_apolo()
