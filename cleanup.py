import os

target_dir = r"D:\AddingUI\Antigravity - Copy\OneClickVM\vm_data"

deleted_count = 0
freed_bytes = 0

for file in os.listdir(target_dir):
    if file.endswith('.vdi'):
        path = os.path.join(target_dir, file)
        size = os.path.getsize(path)
        if size == 2097152 or file == "Ubuntu_OneClick_2f0d2160.vdi":
            os.remove(path)
            deleted_count += 1
            freed_bytes += size
            print(f"Deleted: {file} ({size / (1024 * 1024):.2f} MB)")

print(f"Cleanup complete! Deleted {deleted_count} files, freeing {freed_bytes / (1024 * 1024 * 1024):.2f} GB.")
