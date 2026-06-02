import sys
sys.path.insert(0, 'd:/AddingUI/Antigravity - Copy/OneClickVM')

errors = []

try:
    import frontend.theme
    print("OK: frontend.theme")
except Exception as e:
    errors.append(f"FAIL frontend.theme: {e}")

try:
    import frontend.widgets.status_badge
    print("OK: frontend.widgets.status_badge")
except Exception as e:
    errors.append(f"FAIL status_badge: {e}")

try:
    import frontend.widgets.sidebar
    print("OK: frontend.widgets.sidebar")
except Exception as e:
    errors.append(f"FAIL sidebar: {e}")

try:
    from PyQt5.QtWidgets import QApplication
    import frontend.widgets.vm_card
    print("OK: frontend.widgets.vm_card")
except Exception as e:
    errors.append(f"FAIL vm_card: {e}")

try:
    import frontend.workers.vm_action_worker
    print("OK: frontend.workers.vm_action_worker")
except Exception as e:
    errors.append(f"FAIL vm_action_worker: {e}")

try:
    import frontend.workers.install_worker
    print("OK: frontend.workers.install_worker")
except Exception as e:
    errors.append(f"FAIL install_worker: {e}")

try:
    import frontend.pages.create_vm_page
    print("OK: frontend.pages.create_vm_page")
except Exception as e:
    errors.append(f"FAIL create_vm_page: {e}")

try:
    import frontend.pages.marketplace_page
    print("OK: frontend.pages.marketplace_page")
except Exception as e:
    errors.append(f"FAIL marketplace_page: {e}")

try:
    import frontend.pages.snapshots_page
    print("OK: frontend.pages.snapshots_page")
except Exception as e:
    errors.append(f"FAIL snapshots_page: {e}")

try:
    import frontend.pages.settings_page
    print("OK: frontend.pages.settings_page")
except Exception as e:
    errors.append(f"FAIL settings_page: {e}")

try:
    import frontend.pages.dashboard_page
    print("OK: frontend.pages.dashboard_page")
except Exception as e:
    errors.append(f"FAIL dashboard_page: {e}")

if errors:
    print("\n--- ERRORS ---")
    for err in errors:
        print(err)
else:
    print("\nAll imports successful!")
