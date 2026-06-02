"""Clear all __pycache__ under frontend/ and ui/ so fresh .pyc are built."""
import pathlib, shutil

PROJECT = pathlib.Path(__file__).parent
removed = []
for folder in ("frontend", "ui"):
    for p in (PROJECT / folder).rglob("__pycache__"):
        shutil.rmtree(str(p), ignore_errors=True)
        removed.append(p)

print(f"Cleared {len(removed)} __pycache__ folder(s):")
for p in removed:
    print(f"  {p}")
print("Done — restart the app now.")
