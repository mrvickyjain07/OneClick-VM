"""
backend/snapshot_repository.py
Persistent JSON store for VM snapshot metadata.
"""
import json, uuid, time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from .logger import get_logger

logger = get_logger("SnapshotRepository")


@dataclass
class SnapshotRecord:
    id:            str  = field(default_factory=lambda: uuid.uuid4().hex[:12])
    vm_name:       str  = ""
    vm_uuid:       str  = ""  # VirtualBox machine UUID — preferred identifier
    snapshot_name: str  = ""
    description:   str  = ""
    timestamp:     str  = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    size_bytes:    int  = 0           # estimated or parsed
    status:        str  = "creating"  # creating | completed | failed | orphaned
    has_memory:    bool = False        # live snapshot captured RAM
    vbox_uuid:     str  = ""           # VirtualBox snapshot UUID
    error_msg:     str  = ""

    @property
    def is_orphaned(self) -> bool:
        return self.status == "orphaned"


class SnapshotRepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, SnapshotRecord] = {}
        self._load()

    def _load(self):
        if not self.db_path.exists():
            return
        try:
            data = json.loads(self.db_path.read_text(encoding="utf-8"))
            known = {f for f in SnapshotRecord.__dataclass_fields__}
            for item in data:
                rec = SnapshotRecord(**{k: v for k, v in item.items() if k in known})
                self._records[rec.id] = rec
            logger.info(f"Loaded {len(self._records)} snapshot records")
        except Exception as e:
            logger.error(f"Failed to load snapshot DB: {e}")

    def _save(self):
        try:
            data = [asdict(r) for r in self._records.values()]
            self.db_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except Exception as e:
            logger.error(f"Failed to save snapshot DB: {e}")

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def add(self, rec: SnapshotRecord):
        self._records[rec.id] = rec
        self._save()

    def update(self, rec: SnapshotRecord):
        self._records[rec.id] = rec
        self._save()

    def remove(self, snap_id: str):
        if snap_id in self._records:
            del self._records[snap_id]
            self._save()

    def get(self, snap_id: str) -> Optional[SnapshotRecord]:
        return self._records.get(snap_id)

    def all(self) -> List[SnapshotRecord]:
        return sorted(self._records.values(), key=lambda r: r.timestamp, reverse=True)

    def for_vm(self, vm_name: str) -> List[SnapshotRecord]:
        return [r for r in self.all() if r.vm_name == vm_name]

    def for_vm_uuid(self, vm_uuid: str) -> List[SnapshotRecord]:
        """Return all snapshots linked to a specific VM UUID."""
        return [r for r in self.all() if r.vm_uuid == vm_uuid]

    def orphaned(self) -> List[SnapshotRecord]:
        """Return all snapshots marked as orphaned."""
        return [r for r in self.all() if r.is_orphaned]

    def search(self, query: str = "", vm_filter: str = "All") -> List[SnapshotRecord]:
        q = query.lower().strip()
        results = []
        for rec in self.all():
            if vm_filter not in ("All", "") and rec.vm_name != vm_filter:
                continue
            if q:
                hay = f"{rec.snapshot_name} {rec.vm_name} {rec.description}".lower()
                if q not in hay:
                    continue
            results.append(rec)
        return results

    def counts(self) -> dict:
        all_recs = self.all()
        return {
            "total":     len(all_recs),
            "completed": sum(1 for r in all_recs if r.status == "completed"),
            "creating":  sum(1 for r in all_recs if r.status == "creating"),
            "failed":    sum(1 for r in all_recs if r.status == "failed"),
            "orphaned":  sum(1 for r in all_recs if r.status == "orphaned"),
            "size":      sum(r.size_bytes for r in all_recs),
        }
