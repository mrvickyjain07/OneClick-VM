"""
verify_console_build.py
Quick import check for the new console system.
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

print("\n=== Checking qfluentwidgets classes ===")
from qfluentwidgets import FluentIcon as FIF

def _check_class(cls_name):
    try:
        import qfluentwidgets as qfw
        getattr(qfw, cls_name)
        print(f"  OK   qfw.{cls_name}")
    except AttributeError:
        print(f"  MISS qfw.{cls_name}")
        errors.append((cls_name, f"qfw.{cls_name} not found"))

for cls in ["IndeterminateProgressBar", "ProgressBar", "BodyLabel",
            "StrongBodyLabel", "CaptionLabel", "CardWidget", "PushButton",
            "PrimaryPushButton", "SubtitleLabel", "TitleLabel"]:
    _check_class(cls)

print("\n=== Checking backend ===")
check("vm_session_manager", lambda: __import__("backend.vm_session_manager"))
check("vm_console_service",  lambda: __import__("backend.vm_console_service"))
check("ai_recommendation",   lambda: __import__("backend.ai_recommendation"))

print("\n=== Checking ui.components ===")
check("vm_viewport",         lambda: __import__("ui.components.vm_viewport"))
check("quick_launch_tile",   lambda: __import__("ui.components.quick_launch_tile"))
check("marketplace_card",    lambda: __import__("ui.components.marketplace_card"))
check("machine_card",        lambda: __import__("ui.components.machine_card"))

print("\n=== Checking ui.pages ===")
check("console_page",        lambda: __import__("ui.pages.console_page"))
check("dashboard_page",      lambda: __import__("ui.pages.dashboard_page"))
check("machines_page",       lambda: __import__("ui.pages.machines_page"))
check("marketplace_page",    lambda: __import__("ui.pages.marketplace_page"))
check("settings_page",       lambda: __import__("ui.pages.settings_page"))

print("\n=== Checking ui.dialogs ===")
check("vm_config_dialog",    lambda: __import__("ui.dialogs.vm_config_dialog"))

print("\n=== Checking ui.app ===")
check("ui.app",              lambda: __import__("ui.app"))

print("\n" + "="*52)
if errors:
    print(f"ISSUES ({len(errors)}):")
    for name, msg in errors:
        print(f"  [{name}]  {msg}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED — run:  python main.py")
