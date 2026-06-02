import time
import re
import logging
from PyQt5.QtCore import QThread, pyqtSignal

from backend.vbox_engine import VBoxEngine

logger = logging.getLogger("InstallDetector")

class InstallState:
    LIVE_MODE        = "LIVE_MODE"
    INSTALLING       = "INSTALLING"
    INSTALL_COMPLETE = "INSTALL_COMPLETE"
    FINALIZING       = "FINALIZING"
    READY            = "READY"
    ERROR            = "ERROR"

class InstallDetector(QThread):
    state_changed = pyqtSignal(str)
    
    def __init__(self, vbox_engine: VBoxEngine, vm_name: str, parent=None):
        super().__init__(parent)
        self.vbox_engine = vbox_engine
        self.vm_name = vm_name
        self._stop_flag = False
        self.state = InstallState.LIVE_MODE
        
        self._disk_path = None
        self._start_uptime = 0
        self._was_running = False

    def request_stop(self):
        self._stop_flag = True

    def _set_state(self, new_state):
        if self.state != new_state:
            self.state = new_state
            logger.info(f"[InstallDetector] {self.vm_name} transitioned to {new_state}")
            self.state_changed.emit(new_state)

    def _get_vminfo(self) -> dict:
        """Parse showvminfo --machinereadable into a dictionary."""
        try:
            out = self.vbox_engine.run_cmd(["showvminfo", self.vm_name, "--machinereadable"])
        except Exception as e:
            logger.debug(f"[InstallDetector] Failed to showvminfo: {e}")
            return {}

        info = {}
        for line in out.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip('"').lower()
            val = val.strip('"')
            info[key] = val
        return info

    def is_iso_attached(self, vminfo: dict) -> bool:
        """Detect if an ISO is attached to the VM."""
        # Check any key matching something-1-0 or something-0-0
        for k, v in vminfo.items():
            if re.match(r'^.+-\d+-\d+$', k):
                if v.lower().endswith(".iso"):
                    logger.info("[InstallDetector] ISO detected")
                    return True
        return False

    def get_boot1(self, vminfo: dict) -> str:
        return vminfo.get("boot1", "none").lower()

    def _get_disk_size(self, vminfo: dict) -> int:
        """Get the actual size of the primary disk image (VDI)."""
        if not self._disk_path:
            for k, v in vminfo.items():
                if v.lower().endswith('.vdi') or v.lower().endswith('.vmdk'):
                    self._disk_path = v
                    break
        
        if not self._disk_path:
            return 0
            
        try:
            out = self.vbox_engine.run_cmd(["showmediuminfo", "disk", self._disk_path])
            for line in out.splitlines():
                if line.startswith("Size on disk:"):
                    size_str = line.split(":")[1].strip()
                    size_val = int(size_str.split()[0])
                    return size_val
        except Exception:
            pass
        return 0

    def run(self):
        # Allow VM to start up
        time.sleep(2.0)
        
        vminfo = self._get_vminfo()
        if not self.is_iso_attached(vminfo):
            logger.info("[InstallDetector] No ISO attached. Ready.")
            self._set_state(InstallState.READY)
            return
            
        boot1 = self.get_boot1(vminfo)
        if boot1 != "dvd":
            logger.info(f"[InstallDetector] boot1 is '{boot1}', assuming not live boot.")
            pass

        self._set_state(InstallState.LIVE_MODE)
        self._start_uptime = time.time()
        
        while not self._stop_flag:
            time.sleep(3.0)
            
            vminfo = self._get_vminfo()
            if not vminfo:
                continue
                
            iso_attached = self.is_iso_attached(vminfo)
            if not iso_attached:
                # ISO was manually removed
                self._set_state(InstallState.READY)
                break
                
            disk_size = self._get_disk_size(vminfo)
            disk_size_gb = disk_size / (1024 * 1024 * 1024)
            
            state_str = vminfo.get("vmstate", "unknown")
            is_running = (state_str == "running")
            
            # Disk growth detected
            if self.state == InstallState.LIVE_MODE and disk_size_gb > 1.0:
                logger.info(f"[InstallDetector] Disk growth detected ({disk_size_gb:.2f} GB).")
                self._set_state(InstallState.INSTALLING)
            
            # Detect reboot
            vm_restarted = False
            if self._was_running and not is_running:
                vm_restarted = True
            self._was_running = is_running
            
            # Rule: IF disk size > 5GB AND ISO attached AND VM restarted
            if self.state in (InstallState.LIVE_MODE, InstallState.INSTALLING):
                if iso_attached and disk_size_gb > 5.0 and vm_restarted:
                    logger.info("[InstallDetector] Installation complete condition met.")
                    self._set_state(InstallState.INSTALL_COMPLETE)

            if self.state == InstallState.INSTALL_COMPLETE:
                self._set_state(InstallState.FINALIZING)
                success = self._finalize_installation()
                if success:
                    self._set_state(InstallState.READY)
                    break
                else:
                    self._set_state(InstallState.ERROR)
                    break

    def _finalize_installation(self) -> bool:
        """Perform the automated detachment and boot order fix."""
        logger.info(f"[InstallDetector] Detaching ISO and fixing boot order for {self.vm_name}...")
        try:
            # 1. Power off (retry safely)
            state = self.vbox_engine._get_detailed_state(self.vm_name)
            if state == "running":
                uuid = self.vbox_engine.get_uuid_for_name(self.vm_name) or self.vm_name
                self.vbox_engine.stop_vm_by_uuid(uuid, force=True)
                time.sleep(2)
            
            # 2. Detach ISO (Try IDE, then SATA)
            try:
                self.vbox_engine.run_cmd([
                    "storageattach", self.vm_name,
                    "--storagectl", "IDE",
                    "--port", "1", "--device", "0",
                    "--medium", "none"
                ])
                logger.info("[InstallDetector] Detached ISO on IDE")
            except Exception:
                try:
                    self.vbox_engine.run_cmd([
                        "storageattach", self.vm_name,
                        "--storagectl", "SATA",
                        "--port", "1", "--device", "0",
                        "--medium", "none"
                    ])
                    logger.info("[InstallDetector] Detached ISO on SATA")
                except Exception as e:
                    logger.warning(f"[InstallDetector] Failed to detach ISO: {e}")
            
            # 3. Fix boot order
            self.vbox_engine.run_cmd([
                "modifyvm", self.vm_name,
                "--boot1", "disk", "--boot2", "none",
                "--boot3", "none", "--boot4", "none"
            ])
            logger.info("[InstallDetector] Boot order updated")
            
            # 4. Restart VM
            self.vbox_engine.start_vm(self.vm_name, gui=True)
            logger.info("[InstallDetector] VM restarted")
            return True
            
        except Exception as e:
            logger.error(f"[InstallDetector] Command failure during finalization: {e}")
            return False
