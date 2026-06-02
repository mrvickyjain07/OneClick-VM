import sys
sys.path.insert(0, '.')

errors = []

try:
    from ui.notification_manager import notify
    print("OK: ui.notification_manager")
except Exception as e:
    errors.append(f"FAIL notification_manager: {e}")

try:
    from ui.state_manager import vm_state_manager
    print("OK: ui.state_manager")
except Exception as e:
    errors.append(f"FAIL state_manager: {e}")

try:
    from ui.dialogs.vm_config_dialog import _get_versions
    vers = _get_versions('ubuntu_24_04')
    print(f"OK: vm_config_dialog  ubuntu versions={len(vers)}")
    print(f"   first: {vers[0]['label']}")
except Exception as e:
    errors.append(f"FAIL vm_config_dialog: {e}")

try:
    from ui.workers import VMStartWorker, VMStopWorker, SnapshotDeleteWorker
    print("OK: workers (VMStartWorker, VMStopWorker, SnapshotDeleteWorker)")
except Exception as e:
    errors.append(f"FAIL workers: {e}")

try:
    from backend.snapshot_service import SnapshotService
    print("OK: backend.snapshot_service")
except Exception as e:
    errors.append(f"FAIL snapshot_service: {e}")

if errors:
    print("\n--- ERRORS ---")
    for err in errors:
        print(err)
    sys.exit(1)
else:
    print("\nALL IMPORTS OK")
