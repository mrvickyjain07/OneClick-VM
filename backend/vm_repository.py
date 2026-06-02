"""
backend/vm_repository.py
========================
UUID-keyed VM repository — the canonical persistence layer.

Architecture
------------
VirtualBox is the source of truth.  This repository is a CACHE layer that
reflects what we know about each VM.  The sync engine (vm_sync_service.py)
is responsible for keeping this cache accurate.

Key design decisions
--------------------
- Primary key is UUID (VirtualBox machine UUID), not vm_name.
- vm_name is stored for display and backward compat only.
- state (VMState) tracks RUNNING / STOPPED / MISSING / ERROR / UNKNOWN.
- All mutations are immediately persisted to a JSON file (atomic write).
- A secondary index  {vm_name → uuid}  allows O(1) name-based lookups
  so legacy callers don't need to iterate.

Thread safety
-------------
All public methods acquire self._lock before modifying state.
The poller and sync service both write from background threads.

Storage format: vm_data/vms.json
"""
import json
import threading
import time
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional

from models      import VMState, VMStatus
from .logger     import get_logger

logger = get_logger("VMRepository")


# ─────────────────────────────────────────────────────────────────────────────
# Data record
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class VMEntry:
    """
    Single VM entry in the repository.

    Fields
    ------
    uuid       : VirtualBox machine UUID — primary key
    vm_name    : display name (may change if user renames in VBox)
    os_id      : internal OS identifier (e.g. "ubuntu_24_04")
    os_name    : human OS label (e.g. "Ubuntu")
    os_type_id : VirtualBox OS type string (e.g. "Ubuntu_64")
    created_at : ISO-format timestamp of initial installation
    iso_path   : path to the installer ISO (may be empty post-install)
    ram_mb     : allocated RAM in MB
    cpu_count  : vCPU count
    disk_gb    : primary disk size in GB
    state      : authoritative VMState from last sync
    last_seen  : epoch timestamp of last successful VBox contact
    error_msg  : last error string if state == ERROR or MISSING
    """
    uuid:       str
    vm_name:    str
    os_id:      str      = ""
    os_name:    str      = ""
    os_type_id: str      = ""
    created_at: str      = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    iso_path:   str      = ""
    ram_mb:     int      = 4096
    cpu_count:  int      = 2
    disk_gb:    int      = 30
    state:      str      = VMState.UNKNOWN.value   # stored as string for JSON
    last_seen:  float    = field(default_factory=time.time)
    error_msg:  str      = ""

    @property
    def vm_state(self) -> VMState:
        try:
            return VMState(self.state)
        except ValueError:
            return VMState.UNKNOWN

    @vm_state.setter
    def vm_state(self, s: VMState):
        self.state = s.value

    @property
    def is_missing(self) -> bool:
        return self.state == VMState.MISSING.value

    @property
    def is_running(self) -> bool:
        return self.state == VMState.RUNNING.value


# ─────────────────────────────────────────────────────────────────────────────
# Repository
# ─────────────────────────────────────────────────────────────────────────────

class VMRepository:
    """
    UUID-keyed persistent store for VM entries.

    Usage
    -----
        repo = VMRepository(Path("vm_data/vms.json"))
        repo.upsert(entry)
        entry = repo.get_by_uuid("550e8400-...")
        entries = repo.all()
    """

    def __init__(self, db_path: Path):
        self._path  = db_path
        self._lock  = threading.Lock()
        # Primary store: {uuid → VMEntry}
        self._by_uuid: dict[str, VMEntry] = {}
        # Secondary index: {vm_name → uuid}
        self._by_name: dict[str, str]     = {}
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    # ── Persistence ───────────────────────────────────────────────────────────

    def _load(self):
        if not self._path.exists():
            logger.info("VMRepository: no existing DB at %s — starting fresh", self._path)
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            known_fields = set(VMEntry.__dataclass_fields__)
            for item in raw:
                filtered = {k: v for k, v in item.items() if k in known_fields}
                entry = VMEntry(**filtered)
                self._by_uuid[entry.uuid] = entry
                self._by_name[entry.vm_name] = entry.uuid
            logger.info("VMRepository: loaded %d entries from %s",
                        len(self._by_uuid), self._path)
        except Exception as exc:
            logger.error("VMRepository: failed to load %s: %s", self._path, exc)

    def _save(self):
        """Atomic write — write to .tmp then replace."""
        tmp = self._path.with_suffix(".tmp")
        try:
            data = [asdict(e) for e in self._by_uuid.values()]
            tmp.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except Exception as exc:
            logger.error("VMRepository: failed to save %s: %s", self._path, exc)

    # ── Write operations (thread-safe) ────────────────────────────────────────

    def upsert(self, entry: VMEntry):
        """Insert or update a VMEntry by UUID."""
        with self._lock:
            self._by_uuid[entry.uuid]   = entry
            self._by_name[entry.vm_name] = entry.uuid
            self._save()

    def update_state(self, uuid: str, state: VMState,
                     error_msg: str = "") -> bool:
        """
        Update only the state (and optional error_msg) for a UUID.
        Returns True if the UUID was found, False otherwise.
        """
        with self._lock:
            entry = self._by_uuid.get(uuid)
            if not entry:
                return False
            entry.state     = state.value
            entry.error_msg = error_msg
            if state not in (VMState.MISSING, VMState.ERROR):
                entry.last_seen = time.time()
            self._save()
            return True

    def mark_missing(self, uuid: str):
        """Convenience: mark a VM as MISSING with no error message."""
        self.update_state(uuid, VMState.MISSING)
        logger.warning("VMRepository: marked uuid=%s as MISSING", uuid)

    def remove(self, uuid: str):
        """Remove a VM entry entirely (after confirmed VBox delete)."""
        with self._lock:
            entry = self._by_uuid.pop(uuid, None)
            if entry:
                self._by_name.pop(entry.vm_name, None)
                self._save()
                logger.info("VMRepository: removed uuid=%s ('%s')", uuid, entry.vm_name)

    # ── Read operations ───────────────────────────────────────────────────────

    def get_by_uuid(self, uuid: str) -> Optional[VMEntry]:
        with self._lock:
            return self._by_uuid.get(uuid)

    def get_by_name(self, vm_name: str) -> Optional[VMEntry]:
        with self._lock:
            uuid = self._by_name.get(vm_name)
            return self._by_uuid.get(uuid) if uuid else None

    def all(self) -> list[VMEntry]:
        """Return all entries sorted by created_at descending."""
        with self._lock:
            return sorted(
                self._by_uuid.values(),
                key=lambda e: e.created_at,
                reverse=True,
            )

    def by_state(self, state: VMState) -> list[VMEntry]:
        """Return all entries in the given state."""
        return [e for e in self.all() if e.vm_state == state]

    def missing(self) -> list[VMEntry]:
        return self.by_state(VMState.MISSING)

    def running(self) -> list[VMEntry]:
        return self.by_state(VMState.RUNNING)

    def exists_by_uuid(self, uuid: str) -> bool:
        with self._lock:
            return uuid in self._by_uuid

    def exists_by_name(self, vm_name: str) -> bool:
        with self._lock:
            return vm_name in self._by_name

    # ── Stats ─────────────────────────────────────────────────────────────────

    def counts(self) -> dict[str, int]:
        entries = self.all()
        result: dict[str, int] = {"total": len(entries)}
        for s in VMState:
            result[s.value] = sum(1 for e in entries if e.vm_state == s)
        return result

    def __len__(self) -> int:
        with self._lock:
            return len(self._by_uuid)

    def __repr__(self) -> str:
        return f"<VMRepository path={self._path} entries={len(self)}>"
