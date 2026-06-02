import json
import time
from . import config
from .logger import get_logger

logger = get_logger("VMRegistry")

class VMRegistry:
    def __init__(self):
        config.ensure_directories()
        self.registry_path = config.VM_REGISTRY_PATH
        self._load_registry()

    def _load_registry(self):
        if self.registry_path.exists():
            try:
                with open(self.registry_path, "r") as f:
                    self.vms = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
                self.vms = {}
        else:
            self.vms = {}

    def _save_registry(self):
        try:
            # Atomic write (write to temp then rename)
            temp_path = self.registry_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(self.vms, f, indent=4)
            temp_path.replace(self.registry_path)
        except Exception as e:
            logger.error(f"Failed to save registry: {e}")

    def register_vm(self, vm_data):
        vm_name = vm_data["vm_name"]
        self.vms[vm_name] = vm_data
        self.vms[vm_name]["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.vms[vm_name]["status"] = "Created"
        self._save_registry()
        logger.info(f"Registered VM: {vm_name}")

    def remove_vm(self, vm_name):
        if vm_name in self.vms:
            del self.vms[vm_name]
            self._save_registry()
            logger.info(f"Removed VM from registry: {vm_name}")

    def list_vms(self):
        return list(self.vms.values())

    def update_vm_status(self, vm_name, status):
        if vm_name in self.vms:
            self.vms[vm_name]["status"] = status
            self._save_registry()
