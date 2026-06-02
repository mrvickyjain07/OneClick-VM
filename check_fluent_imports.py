import sys
sys.path.insert(0, 'd:/AddingUI/Antigravity - Copy/OneClickVM')

errors = []

try:
    import frontend.pages.fluent_dashboard
    print("OK: fluent_dashboard")
except Exception as e:
    errors.append(f"FAIL fluent_dashboard: {e}")

try:
    import frontend.pages.fluent_marketplace
    print("OK: fluent_marketplace")
except Exception as e:
    errors.append(f"FAIL fluent_marketplace: {e}")

try:
    import frontend.pages.fluent_create_vm
    print("OK: fluent_create_vm")
except Exception as e:
    errors.append(f"FAIL fluent_create_vm: {e}")

try:
    import frontend.pages.fluent_snapshots
    print("OK: fluent_snapshots")
except Exception as e:
    errors.append(f"FAIL fluent_snapshots: {e}")

try:
    import frontend.pages.fluent_settings
    print("OK: fluent_settings")
except Exception as e:
    errors.append(f"FAIL fluent_settings: {e}")

try:
    import frontend.app
    print("OK: app")
except Exception as e:
    errors.append(f"FAIL app: {e}")

if errors:
    print("\n--- ERRORS ---")
    for err in errors:
        print(err)
else:
    print("\nAll Fluent imports successful!")
