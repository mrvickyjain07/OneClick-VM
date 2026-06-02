"""
backend/machines_db.py
Persistent storage for installed VM records (machines.json).
Completely separate from marketplace template state.
"""
import json
import time
from pathlib import Path
from models import VMRecord, VMStatus
from .logger import get_logger

logger = get_logger("MachinesDB")


class MachinesDB:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, dict] = {}
        self._load()

    # ── Persistence ────────────────────────────────────────────────────────
    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self._records = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load machines.json: {e}")
                self._records = {}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._records, f, indent=4)
            tmp.replace(self.path)
        except Exception as e:
            logger.error(f"Failed to save machines.json: {e}")

    # ── CRUD ───────────────────────────────────────────────────────────────
    def add(self, rec: VMRecord):
        self._records[rec.vm_name] = {
            "vm_name":   rec.vm_name,
            "os_id":     rec.os_id,
            "os_name":   rec.os_name,
            "created_at":rec.created_at,
            "iso_path":  rec.iso_path,
            "status":    rec.status.value,
            "ram_mb":    rec.ram_mb,
            "cpu_count": rec.cpu_count,
            "disk_gb":   rec.disk_gb,
            "uuid":      rec.uuid,         # VirtualBox machine UUID
        }
        self._save()
        logger.info(f"Registered machine: {rec.vm_name}")

    def remove(self, vm_name: str):
        if vm_name in self._records:
            del self._records[vm_name]
            self._save()
            logger.info(f"Removed machine: {vm_name}")

    def update_status(self, vm_name: str, status: VMStatus):
        if vm_name in self._records:
            self._records[vm_name]["status"] = status.value
            self._save()

    def set_uuid(self, vm_name: str, uuid: str):
        """Back-fill the VirtualBox UUID into an existing record."""
        if vm_name in self._records:
            self._records[vm_name]["uuid"] = uuid
            self._save()
            logger.debug(f"set_uuid: '{vm_name}' → {uuid}")

    def all(self) -> list[VMRecord]:
        out = []
        for d in self._records.values():
            out.append(VMRecord(
                vm_name   = d["vm_name"],
                os_id     = d.get("os_id", ""),
                os_name   = d.get("os_name", ""),
                created_at= d.get("created_at", ""),
                iso_path  = d.get("iso_path", ""),
                status    = VMStatus(d.get("status", "stopped")),
                ram_mb    = d.get("ram_mb", 4096),
                cpu_count = d.get("cpu_count", 2),
                disk_gb   = d.get("disk_gb", 30),
                uuid      = d.get("uuid", ""),
            ))
        return out

    def get(self, vm_name: str) -> VMRecord | None:
        d = self._records.get(vm_name)
        if not d:
            return None
        return VMRecord(
            vm_name   = d["vm_name"],
            os_id     = d.get("os_id", ""),
            os_name   = d.get("os_name", ""),
            created_at= d.get("created_at", ""),
            iso_path  = d.get("iso_path", ""),
            status    = VMStatus(d.get("status", "stopped")),
            ram_mb    = d.get("ram_mb", 4096),
            cpu_count = d.get("cpu_count", 2),
            disk_gb   = d.get("disk_gb", 30),
            uuid      = d.get("uuid", ""),
        )

    def exists(self, vm_name: str) -> bool:
        return vm_name in self._records
