"""
backend/vm_state_poller.py
==========================
Fast, non-blocking VM state tracking via a dedicated QThread.

Architecture
------------
- Uses `VBoxManage list vms` + `list runningvms` (two fast calls per cycle)
  instead of per-VM showvminfo calls that could block for 60+ seconds.
- Maintains a thread-safe in-memory cache:
      {vm_name → "running" | "stopped" | "missing" | "unknown"}
- Also maintains a UUID cache: {uuid → state_str}  for UUID-first callers.
- Emits `states_updated` signal after every successful poll so widgets
  can refresh without touching VBox themselves.
- Detects MISSING VMs (in DB but not in VBox registry) and emits
  `vm_missing_detected` so the UI can surface a warning.

Usage
-----
    poller = VMStatePoller(vbox_engine, machines_db)
    poller.states_updated.connect(my_slot)
    poller.vm_missing_detected.connect(on_missing)
    poller.start()
    ...
    state = poller.get_cached_state("MyVM")   # instant — no subprocess
    state = poller.get_cached_state_by_uuid("550e8400-...")
    ...
    poller.stop()
"""
import time
import threading
from PyQt5.QtCore import QThread, pyqtSignal

from .logger import get_logger

logger = get_logger("VMStatePoller")

POLL_INTERVAL  = 4     # seconds between polls
CMD_TIMEOUT    = 5     # max seconds for list vms / runningvms
MAX_RETRIES    = 2     # retries on transient errors
SLOW_THRESHOLD = 2.0   # log warning if command exceeds this (seconds)


class VMStatePoller(QThread):
    """
    Background poller that keeps vm_state_cache up-to-date using
    `VBoxManage list vms` + `list runningvms`.

    Signals
    -------
    states_updated(dict)         emitted after every successful poll
                                 dict = {vm_name: state_str}

    vm_missing_detected(list)    emitted when VMs in DB are absent from VBox
                                 list = [vm_name, ...]
    """
    states_updated      = pyqtSignal(dict)   # {vm_name: state_str}
    vm_missing_detected = pyqtSignal(list)   # [vm_name, ...]

    def __init__(self, vbox_engine, machines_db, parent=None):
        super().__init__(parent)
        self.vbox        = vbox_engine
        self.machines_db = machines_db
        self._lock       = threading.Lock()
        # name → state_str
        self._cache: dict[str, str] = {}
        # uuid → state_str (populated when list vms is available)
        self._uuid_cache: dict[str, str] = {}
        self._running    = False
        self.setObjectName("VMStatePoller")

    # ── Public API (safe to call from any thread) ─────────────────────────

    def get_cached_state(self, vm_name: str) -> str:
        """Return cached state by name instantly — never blocks."""
        with self._lock:
            return self._cache.get(vm_name, "unknown")

    def get_cached_state_by_uuid(self, uuid: str) -> str:
        """Return cached state by UUID instantly — never blocks."""
        with self._lock:
            return self._uuid_cache.get(uuid.lower(), "unknown")

    def get_all_cached(self) -> dict:
        """Return a snapshot of the full name-keyed cache."""
        with self._lock:
            return dict(self._cache)

    def set_state(self, vm_name: str, state: str):
        """
        Optimistically update a single VM's state in the cache.
        Call this immediately after start_vm / stop_vm so the UI
        reflects the new state before the next poll fires.
        """
        with self._lock:
            self._cache[vm_name] = state
        self.states_updated.emit(self.get_all_cached())

    def set_state_by_uuid(self, uuid: str, state: str):
        """Optimistically update state by UUID."""
        with self._lock:
            self._uuid_cache[uuid.lower()] = state

    def stop(self):
        """Signal the poll loop to exit cleanly."""
        self._running = False

    # ── QThread entry point ───────────────────────────────────────────────

    def run(self):
        self._running = True
        logger.info(
            "VMStatePoller started (interval=%ds, timeout=%ds)",
            POLL_INTERVAL, CMD_TIMEOUT,
        )

        # Seed cache with "unknown" for all known VMs so callers get
        # a valid entry immediately (before the first poll completes).
        self._seed_cache()

        while self._running:
            self._poll()
            # Sleep in small increments so stop() is responsive
            for _ in range(POLL_INTERVAL * 10):
                if not self._running:
                    break
                time.sleep(0.1)

        logger.info("VMStatePoller stopped")

    # ── Internal helpers ──────────────────────────────────────────────────

    def _seed_cache(self):
        """Pre-populate name cache with 'unknown' for every registered VM."""
        try:
            vms = self.machines_db.all()
            with self._lock:
                for rec in vms:
                    if rec.vm_name not in self._cache:
                        self._cache[rec.vm_name] = "unknown"
                    if rec.uuid and rec.uuid not in self._uuid_cache:
                        self._uuid_cache[rec.uuid.lower()] = "unknown"
        except Exception as exc:
            logger.warning("Could not seed cache: %s", exc)

    def _poll(self):
        """
        Single poll iteration.

        1. Call `list vms`       → full registry {uuid: name}
        2. Call `list runningvms` → running {uuid: name}
        3. Compute state per known VM
        4. Detect MISSING VMs (in DB but not in VBox)
        5. Update caches; emit signals if anything changed
        """
        t0 = time.monotonic()

        # ── Query VBox ─────────────────────────────────────────────────
        all_vms      = self._safe_list_all_vms()
        running_uuids = self._safe_list_running_uuids()

        elapsed = time.monotonic() - t0
        if elapsed > SLOW_THRESHOLD:
            logger.warning("poll VBox calls took %.1fs (slow!)", elapsed)
        else:
            logger.debug("poll VBox calls took %.3fs", elapsed)

        if all_vms is None:
            # Total failure — keep existing cache, do not emit
            return

        # ── Read known VMs from DB ─────────────────────────────────────
        try:
            db_records = self.machines_db.all()
        except Exception as exc:
            logger.warning("Cannot read machines DB in poller: %s", exc)
            return

        vbox_names  = set(all_vms.values())
        vbox_uuids  = set(all_vms.keys())
        running_uuids = running_uuids or set()

        new_cache      : dict[str, str] = {}
        new_uuid_cache : dict[str, str] = {}
        missing_vms    : list[str]      = []

        for rec in db_records:
            uuid = (rec.uuid or "").lower()

            # Determine state: check by UUID first, fall back to name
            if uuid and uuid in vbox_uuids:
                state = "running" if uuid in running_uuids else "stopped"
            elif rec.vm_name in vbox_names:
                # UUID not known or not matching, but name is in VBox
                # Try to find UUID from the all_vms dict
                found_uuid = next(
                    (u for u, n in all_vms.items() if n == rec.vm_name), None
                )
                state = "running" if (found_uuid and found_uuid in running_uuids) else "stopped"
            else:
                # Not in VBox at all → MISSING
                state = "missing"
                missing_vms.append(rec.vm_name)

            new_cache[rec.vm_name] = state
            if uuid:
                new_uuid_cache[uuid] = state

        # ── Update caches atomically ───────────────────────────────────
        changed = False
        with self._lock:
            for vm_name, state in new_cache.items():
                if self._cache.get(vm_name) != state:
                    changed = True
                self._cache[vm_name] = state
            for uuid_k, state in new_uuid_cache.items():
                self._uuid_cache[uuid_k] = state

        # ── Emit signals ───────────────────────────────────────────────
        if changed:
            logger.debug("VM states updated: %s", new_cache)
            self.states_updated.emit(dict(new_cache))

        if missing_vms:
            logger.warning("Missing VMs detected: %s", missing_vms)
            self.vm_missing_detected.emit(missing_vms)

    def _safe_list_all_vms(self) -> dict | None:
        """
        Run `VBoxManage list vms` with retries.
        Returns {uuid: name} dict or None on total failure.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self.vbox.list_all_vms()
            except RuntimeError as exc:
                err = str(exc)
                if "timed out" in err:
                    logger.warning(
                        "list vms timed out (attempt %d/%d)", attempt, MAX_RETRIES
                    )
                else:
                    logger.warning(
                        "list vms failed (attempt %d/%d): %s",
                        attempt, MAX_RETRIES, err,
                    )
                if attempt < MAX_RETRIES:
                    time.sleep(1)
            except Exception as exc:
                logger.error("Unexpected error in list_all_vms: %s", exc)
                return None

        # Fallback: empty dict means all known VMs appear as MISSING.
        # Return None to signal total failure (keep stale cache).
        return None

    def _safe_list_running_uuids(self) -> set | None:
        """
        Run `VBoxManage list runningvms` with retries.
        Returns set of running UUIDs or None on total failure.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self.vbox.list_running_uuids()
            except RuntimeError as exc:
                err = str(exc)
                logger.warning(
                    "list runningvms failed (attempt %d/%d): %s",
                    attempt, MAX_RETRIES, err,
                )
                if attempt < MAX_RETRIES:
                    time.sleep(1)
            except Exception as exc:
                logger.error("Unexpected error in list_running_uuids: %s", exc)
                return None

        return None
