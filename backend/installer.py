import time
import uuid
from . import config
from .logger import get_logger
from .template_manager import TemplateManager
from .iso_manager import ISOManager
from .vbox_engine import VBoxEngine
from .vm_registry import VMRegistry

logger = get_logger("Installer")

class Installer:
    def __init__(self):
        self.template_manager = TemplateManager()
        self.template_manager.load_templates()
        self.iso_manager = ISOManager()
        self.vbox = VBoxEngine()
        self.registry = VMRegistry()

    def install_os(self, os_id, progress_callback=None, log_callback=None, pause_check_callback=None,
                   ram_mb: int = None, cpu_count: int = None, disk_gb: int = None):
        """
        Orchestrates the entire installation process.

        Args:
            os_id:             The OS template identifier.
            progress_callback: Called with progress dicts during ISO download.
            log_callback:      Called with log strings for the UI console.
            ram_mb:            RAM override (MB). None = use template default.
            cpu_count:         CPU count override. None = use template default.
            disk_gb:           Disk size override (GB). None = use template default.
        """
        def log(msg):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        try:
            # 1. Load Template
            template = self.template_manager.get_template(os_id)
            if not template:
                raise ValueError(f"Unknown OS ID: {os_id}")

            # Apply resource overrides (UI sliders take precedence over template)
            effective_ram  = ram_mb    if ram_mb    is not None else template["ram_mb"]
            effective_cpu  = cpu_count if cpu_count is not None else template["cpu"]
            effective_disk = disk_gb   if disk_gb   is not None else template["disk_gb"]

            log(f"Starting installation for {template['os_name']}...")
            log(f"Resources: RAM={effective_ram} MB  CPU={effective_cpu}  Disk={effective_disk} GB")

            # 2. Check VirtualBox
            if not self.vbox.is_virtualbox_installed():
                 raise RuntimeError("VirtualBox is not installed!")
            log("VirtualBox detected.")

            # 3. Download ISO
            iso_path = self.iso_manager.get_iso_path(template)
            if not self.iso_manager.iso_exists(template):
                log("Downloading ISO... (this may take a while)")
                self.iso_manager.download_iso(
                    template["iso_url"],
                    iso_path,
                    progress_callback=progress_callback,
                    pause_check_callback=pause_check_callback
                )
            else:
                log("ISO found in cache.")
                if progress_callback:
                    progress_callback({'percentage': 100, 'speed_mb_s': 0, 'eta_seconds': 0})

            # 4. Create VM Name
            uid     = str(uuid.uuid4())[:8]
            vm_name = f"{template['vm_name_prefix']}_{uid}"

            # 5. Create VM
            log(f"Creating VM: {vm_name}")
            self.vbox.create_vm(vm_name, os_type=template.get("os_type_id", "Other"))
            self.vbox.set_vm_resources(vm_name, effective_ram, effective_cpu)
            self.vbox.attach_storage_controller(vm_name, "SATA Controller", "IntelAHCI")

            # 6. Create Media
            disk_filename = f"{vm_name}.vdi"
            disk_path = config.VM_DATA_DIR / disk_filename
            log(f"Creating Disk: {disk_path} ({effective_disk} GB)")
            self.vbox.create_disk(vm_name, effective_disk, disk_path)

            # 7. Attach Media
            log("Attaching Disk and ISO...")
            self.vbox.attach_disk(vm_name, disk_path, controller="SATA Controller", port=0)
            self.vbox.attach_iso(vm_name, iso_path, controller="SATA Controller", port=1)

            # 8. Network
            self.vbox.set_network_nat(vm_name)

            # 9. Start VM
            log("Launching VM...")
            self.vbox.start_vm(vm_name)

            # 10. Register
            self.registry.register_vm({
                "vm_name":  vm_name,
                "os_id":    os_id,
                "ram_mb":   effective_ram,
                "cpu":      effective_cpu,
                "disk_gb":  effective_disk,
                "iso_path": str(iso_path),
                "disk_path":str(disk_path)
            })

            log("Installation Successful!")
            return {
                "success": True,
                "vm_name": vm_name,
                "message": "VM Launched Successfully"
            }

        except Exception as e:
            logger.exception("Installation failed")
            if log_callback:
                log_callback(f"Error: {str(e)}")
            return {
                "success": False,
                "message": str(e)
            }
