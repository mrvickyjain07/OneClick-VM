"""
check_new_backend.py
Quick import verification for the new VBox integration layer.
Run from project root: python check_new_backend.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

MODULES = [
    ("models",                       "models"),
    ("backend.vbox_error",           "vbox_error"),
    ("backend.vbox_engine",          "vbox_engine"),
    ("backend.vm_repository",        "vm_repository"),
    ("backend.vm_sync_service",      "vm_sync_service"),
    ("backend.health_check",         "health_check"),
    ("backend.snapshot_repository",  "snapshot_repository"),
    ("backend.snapshot_service",     "snapshot_service"),
    ("backend.machines_db",          "machines_db"),
    ("backend.vm_service",           "vm_service"),
    ("backend.vm_state_poller",      "vm_state_poller"),
]

errors = []
for mod, label in MODULES:
    try:
        __import__(mod)
        print(f"  OK    {label}")
    except Exception as exc:
        print(f"  FAIL  {label}: {exc}")
        errors.append((label, str(exc)))

print()
if errors:
    print(f"IMPORT ERRORS ({len(errors)}):")
    for lbl, err in errors:
        print(f"  {lbl}: {err}")
    sys.exit(1)
else:
    print("All backend imports OK")
    sys.exit(0)
