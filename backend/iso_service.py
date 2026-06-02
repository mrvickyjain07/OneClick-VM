"""
backend/iso_service.py
Orchestrates ISO import, mount, unmount, and deletion.
Separates business logic from the UI layer.
"""
import shutil
import time
import uuid
from pathlib import Path

from .logger          import get_logger
from .iso_repository  import ISORepository, ISORecord
from .iso_validator   import validate_iso_file, guess_category, guess_vendor, format_size
from .vbox_engine     import VBoxEngine

logger = get_logger("ISOService")


class ISOService:
    def __init__(self, repo: ISORepository, library_dir: Path):
        self.repo        = repo
        self.library_dir = library_dir
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.vbox        = VBoxEngine()

    # ── Import ────────────────────────────────────────────────────────────────

    def import_iso(
        self,
        source_path:       str,
        progress_callback  = None,   # (int 0-100) → None
        cancel_check       = None,   # () → bool
    ) -> ISORecord:
        """
        Validate → copy to managed library folder → register in repo.
        Raises ValueError on validation failure.
        Raises InterruptedError if cancel_check() returns True mid-copy.
        """
        ok, msg = validate_iso_file(source_path)
        if not ok:
            raise ValueError(msg)

        src  = Path(source_path)
        dest = self._unique_dest(src)

        total_size = src.stat().st_size
        copied     = 0
        CHUNK      = 1024 * 1024  # 1 MB chunks

        with open(src, "rb") as fin, open(dest, "wb") as fout:
            while True:
                if cancel_check and cancel_check():
                    dest.unlink(missing_ok=True)
                    raise InterruptedError("Import cancelled by user.")
                chunk = fin.read(CHUNK)
                if not chunk:
                    break
                fout.write(chunk)
                copied += len(chunk)
                if progress_callback and total_size > 0:
                    progress_callback(int(copied * 100 / total_size))

        rec = ISORecord(
            id           = uuid.uuid4().hex[:12],
            name         = src.stem,
            version      = "",
            vendor       = guess_vendor(src.name),
            description  = "Manually imported ISO image.",
            file_path    = str(dest),
            file_size    = total_size,
            added_date   = time.strftime("%Y-%m-%d %H:%M"),
            file_type    = src.suffix.lower(),
            status       = "downloaded",
            category     = guess_category(src.name),
            tags         = [],
            mount_status = "unmounted",
        )
        self.repo.add(rec)
        logger.info(f"Imported ISO '{rec.name}' → {dest}")
        return rec

    # ── Mount / Unmount ───────────────────────────────────────────────────────

    def mount_to_vm(self, iso_id: str, vm_name: str):
        """Attach an ISO from the library to a VM's DVD drive via VBoxManage."""
        rec = self._get_or_raise(iso_id)
        if not Path(rec.file_path).exists():
            raise FileNotFoundError(f"ISO file missing on disk: {rec.file_path}")

        self.vbox.attach_iso(vm_name, Path(rec.file_path), controller="SATA", port=1)
        rec.mount_status  = "mounted"
        rec.mounted_to_vm = vm_name
        rec.status        = "mounted"
        self.repo.update(rec)
        logger.info(f"Mounted '{rec.name}' to VM '{vm_name}'")

    def unmount_from_vm(self, iso_id: str):
        """Detach an ISO from its currently mounted VM."""
        rec = self._get_or_raise(iso_id)
        if rec.mount_status != "mounted":
            return
        vm_name = rec.mounted_to_vm
        try:
            self.vbox.detach_iso(vm_name, controller="SATA", port=1)
        except Exception as e:
            logger.warning(f"Detach may have already happened: {e}")
        rec.mount_status  = "unmounted"
        rec.mounted_to_vm = ""
        rec.status        = "downloaded"
        self.repo.update(rec)
        logger.info(f"Unmounted '{rec.name}' from VM '{vm_name}'")

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_iso(self, iso_id: str, delete_file: bool = True):
        rec = self._get_or_raise(iso_id)
        if delete_file:
            try:
                Path(rec.file_path).unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Could not delete ISO file: {e}")
        self.repo.remove(iso_id)
        logger.info(f"Deleted ISO record '{rec.name}'")

    # ── Query ─────────────────────────────────────────────────────────────────

    def all_isos(self)            -> list: return self.repo.all()
    def search(self, q, cat="All") -> list: return self.repo.search(q, cat)
    def counts(self)              -> dict: return self.repo.counts()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_or_raise(self, iso_id: str) -> ISORecord:
        rec = self.repo.get(iso_id)
        if not rec:
            raise ValueError(f"ISO '{iso_id}' not found in library.")
        return rec

    def _unique_dest(self, src: Path) -> Path:
        dest    = self.library_dir / src.name
        counter = 1
        while dest.exists():
            dest = self.library_dir / f"{src.stem}_{counter}{src.suffix}"
            counter += 1
        return dest
