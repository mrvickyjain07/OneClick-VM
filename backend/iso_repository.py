"""
backend/iso_repository.py
Persistent JSON store for manually managed ISO records.
"""
import json
import uuid
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from .logger import get_logger

logger = get_logger("ISORepository")


@dataclass
class ISORecord:
    id:               str  = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name:             str  = ""
    version:          str  = ""
    vendor:           str  = ""
    description:      str  = ""
    file_path:        str  = ""
    file_size:        int  = 0          # bytes
    added_date:       str  = ""
    file_type:        str  = ".iso"
    checksum:         str  = ""
    checksum_status:  str  = "pending"  # pending | valid | invalid
    mount_status:     str  = "unmounted"  # unmounted | mounted
    status:           str  = "downloaded" # importing | downloading | downloaded | mounted | error
    category:         str  = "Custom"   # Linux | Windows | Utility | Security | Custom
    tags:             list = field(default_factory=list)
    mounted_to_vm:    str  = ""
    error_msg:        str  = ""


class ISORepository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, ISORecord] = {}
        self._load()

    def _load(self):
        if not self.db_path.exists():
            return
        try:
            data = json.loads(self.db_path.read_text(encoding="utf-8"))
            for item in data:
                # Forward-compat: ignore unknown keys
                known = {f.name for f in ISORecord.__dataclass_fields__.values()}
                clean = {k: v for k, v in item.items() if k in known}
                rec = ISORecord(**clean)
                self._records[rec.id] = rec
            logger.info(f"Loaded {len(self._records)} ISO records")
        except Exception as e:
            logger.error(f"Failed to load ISO DB: {e}")

    def _save(self):
        try:
            data = [asdict(r) for r in self._records.values()]
            self.db_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"Failed to save ISO DB: {e}")

    # ── CRUD ─────────────────────────────────────────────────────────────────

    def add(self, rec: ISORecord):
        self._records[rec.id] = rec
        self._save()
        logger.info(f"Registered ISO: {rec.name} ({rec.id})")

    def update(self, rec: ISORecord):
        self._records[rec.id] = rec
        self._save()

    def remove(self, iso_id: str):
        if iso_id in self._records:
            del self._records[iso_id]
            self._save()

    def get(self, iso_id: str) -> Optional[ISORecord]:
        return self._records.get(iso_id)

    def all(self) -> List[ISORecord]:
        return list(self._records.values())

    def search(self, query: str = "", category: str = "All") -> List[ISORecord]:
        q = query.lower().strip()
        results = []
        for rec in self._records.values():
            if category not in ("All", "") and rec.category != category:
                continue
            if q:
                haystack = (
                    f"{rec.name} {rec.version} {rec.vendor} "
                    f"{rec.description} {' '.join(rec.tags)}"
                ).lower()
                if q not in haystack:
                    continue
            results.append(rec)
        return sorted(results, key=lambda r: r.added_date, reverse=True)

    # ── Summary counts ────────────────────────────────────────────────────────

    def counts(self) -> dict:
        all_recs = self.all()
        return {
            "total":       len(all_recs),
            "downloaded":  sum(1 for r in all_recs if r.status == "downloaded"),
            "importing":   sum(1 for r in all_recs if r.status == "importing"),
            "mounted":     sum(1 for r in all_recs if r.status == "mounted"),
            "error":       sum(1 for r in all_recs if r.status == "error"),
        }
