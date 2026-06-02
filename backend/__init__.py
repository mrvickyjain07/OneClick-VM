"""
backend/__init__.py
Package-level exports for the backend module.

New production-grade VirtualBox integration layer:
  vbox_error      — structured error classification
  vm_repository   — UUID-keyed VM repository (authoritative cache)
  vm_sync_service — startup sync engine (VBox → DB)
  health_check    — validate_vm / sync_vms / repair_state / get_health_report

Legacy modules preserved for backward compatibility:
  vbox_engine, machines_db, vm_service, vm_state_poller,
  snapshot_repository, snapshot_service
"""
