"""
verify_new_app.py  — Run from the project root to catch all import errors.
Usage: python verify_new_app.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

errors = []

def check(label, fn):
    try:
        fn()
        print(f"  OK   {label}")
    except Exception as e:
        print(f"  FAIL {label}: {e}")
        errors.append((label, str(e)))

print("\n=== Checking qfluentwidgets icons ===")
from qfluentwidgets import FluentIcon as FIF
for icon in ["HOME", "CLOUD", "IOT", "COMMAND_PROMPT", "SETTING",
             "DOWNLOAD", "PLAY", "SEND", "POWER_BUTTON", "DELETE",
             "SYNC", "FOLDER_ADD", "ACCEPT", "MORE", "UP"]:
    if hasattr(FIF, icon):
        print(f"  OK   FIF.{icon}")
    else:
        print(f"  MISS FIF.{icon}  ← will fallback")
        # Not a hard error — we'll handle in code

print("\n=== Checking backend ===")
check("backend.config",      lambda: __import__("backend.config"))
check("backend.iso_manager", lambda: __import__("backend.iso_manager"))
check("backend.machines_db", lambda: __import__("backend.machines_db"))
check("backend.vm_service",  lambda: __import__("backend.vm_service"))

print("\n=== Checking models ===")
check("models",              lambda: __import__("models"))

print("\n=== Checking ui.workers ===")
check("ui.workers",          lambda: __import__("ui.workers"))

print("\n=== Checking ui.components ===")
check("marketplace_card",    lambda: __import__("ui.components.marketplace_card"))
check("machine_card",        lambda: __import__("ui.components.machine_card"))

print("\n=== Checking ui.pages ===")
check("dashboard_page",      lambda: __import__("ui.pages.dashboard_page"))
check("marketplace_page",    lambda: __import__("ui.pages.marketplace_page"))
check("machines_page",       lambda: __import__("ui.pages.machines_page"))
check("console_page",        lambda: __import__("ui.pages.console_page"))
check("settings_page",       lambda: __import__("ui.pages.settings_page"))

print("\n=== Checking ui.app ===")
check("ui.app",              lambda: __import__("ui.app"))

print("\n" + "="*50)
if errors:
    print(f"ISSUES ({len(errors)}):")
    for name, msg in errors:
        print(f"  [{name}]  {msg}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED — run:  python main.py")
