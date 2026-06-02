"""
backend/vbox_engine.py
======================
Low-level VBoxManage command wrapper — production-grade, UUID-first.

Design principles
-----------------
1.  VirtualBox is the source of truth.
2.  Every destructive operation validates VM existence (by UUID) first.
3.  All commands run via subprocess.Popen with a configurable timeout.
4.  Every call is timed and logged (command, stdout, stderr, elapsed).
5.  Non-zero return codes are classified by vbox_error.classify_error()
    into structured VBoxError objects before raising RuntimeError.
6.  CREATE_NO_WINDOW suppresses the black console flash on Windows.

UUID-first API
--------------
    list_all_vms()          → dict[uuid, name]   — parse `list vms`
    validate_vm(uuid)       → bool               — existence check (fast)
    start_vm_by_uuid(uuid)  → None
    stop_vm_by_uuid(uuid)   → None
    delete_vm_by_uuid(uuid) → None

Legacy name-based methods are preserved for backward compatibility.
"""
import re
import subprocess
import shutil
import os
import time
from typing import Optional

from .logger      import get_logger
from .vbox_error  import (
    classify_error, VBoxError, VMNotFoundException,
    SnapshotNotFoundException, VBoxNotInstalledError,
    VBOX_E_OBJECT_NOT_FOUND,
)

logger = get_logger("VBoxEngine")

# Windows: hide the console flash for background subprocesses
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Default timeouts (seconds)
_T_FAST   =  5   # list vms, show state
_T_START  = 15   # startvm
_T_STOP   = 10   # controlvm
_T_SNAP   = 360  # take snapshot (live / large disk)
_T_EXPORT = 600  # export OVA

# VBox error codes that indicate a transient machine lock — safe to retry
_LOCK_ERRORS = (
    "VBOX_E_INVALID_OBJECT_STATE",
    "E_ACCESSDENIED",
    "already locked",
    "machine is not mutable",
    "locked for reading",
)


def _retry_on_lock(retries: int = 3, delay: float = 0.6):
    """
    Decorator: retry the wrapped method when VirtualBox raises a transient
    machine-lock error (VBOX_E_INVALID_OBJECT_STATE / E_ACCESSDENIED).
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, retries + 1):
                try:
                    return fn(*args, **kwargs)
                except RuntimeError as exc:
                    msg = str(exc)
                    if any(tag in msg for tag in _LOCK_ERRORS):
                        logger.warning(
                            "Lock error on attempt %d/%d for %s: %s",
                            attempt, retries, fn.__name__, msg[:120]
                        )
                        time.sleep(delay)
                        last_exc = exc
                    else:
                        raise   # Non-lock error — propagate immediately
            raise last_exc
        wrapper.__wrapped__ = fn
        return wrapper
    return decorator


class VBoxEngine:
    """
    Thin wrapper around VBoxManage.

    All public methods raise RuntimeError (or VMNotFoundException /
    SnapshotNotFoundException) on failure.  Callers should catch those
    and handle accordingly.
    """

    def __init__(self):
        self.vbox_manage_cmd: Optional[str] = self._find_vbox_manage()

    # ─────────────────────────────────────────────────────────────────────────
    # Discovery
    # ─────────────────────────────────────────────────────────────────────────

    def _find_vbox_manage(self) -> Optional[str]:
        if shutil.which("VBoxManage"):
            return "VBoxManage"
        candidates = [
            r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
            r"C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe",
            "/usr/bin/VBoxManage",
            "/usr/local/bin/VBoxManage",
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def is_virtualbox_installed(self) -> bool:
        return self.vbox_manage_cmd is not None

    def _require_vbox(self):
        if not self.vbox_manage_cmd:
            raise VBoxNotInstalledError(
                "VirtualBox is not installed or VBoxManage was not found on PATH."
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Core executor
    # ─────────────────────────────────────────────────────────────────────────

    def run_cmd(self, args: list, timeout: int = _T_FAST,
                vm_uuid: str = None, vm_name: str = None) -> str:
        """
        Run a VBoxManage sub-command and return stdout as a string.

        Parameters
        ----------
        args     : argument list after 'VBoxManage'  (each item → str)
        timeout  : seconds before the process is killed
        vm_uuid  : optional — attached to error context
        vm_name  : optional — attached to error context

        Raises
        ------
        VMNotFoundException  if stderr contains VBOX_E_OBJECT_NOT_FOUND
        RuntimeError         for all other non-zero exits or timeouts
        """
        self._require_vbox()

        cmd     = [self.vbox_manage_cmd] + [str(a) for a in args]
        subcmd  = args[0] if args else "?"
        t0      = time.monotonic()
        proc    = None

        logger.debug("RUN [%ds]  %s", timeout, " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=_NO_WINDOW,
            )
            stdout, stderr = proc.communicate(timeout=timeout)

        except subprocess.TimeoutExpired:
            if proc:
                try:
                    proc.kill()
                    proc.communicate()
                except Exception:
                    pass
            elapsed = time.monotonic() - t0
            logger.warning(
                "TIMEOUT %.1fs  cmd=%s", elapsed, " ".join(cmd)
            )
            raise RuntimeError(
                f"VBoxManage timed out after {timeout}s\nCommand: {' '.join(cmd)}"
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to launch VBoxManage: {exc}") from exc

        elapsed = time.monotonic() - t0

        # ── Timing log ────────────────────────────────────────────────────
        if elapsed > 2.0:
            logger.warning("SLOW %.1fs  sub-cmd=%s", elapsed, subcmd)
        else:
            logger.debug("OK   %.3fs  sub-cmd=%s", elapsed, subcmd)

        if stderr.strip():
            logger.debug("stderr (non-fatal): %.200s", stderr.strip())

        # ── Non-zero return code ──────────────────────────────────────────
        if proc.returncode != 0:
            err_text = (stderr or "").strip()
            logger.error(
                "rc=%d  cmd=%s\nstderr: %.300s",
                proc.returncode, " ".join(cmd), err_text,
            )
            vbe = classify_error(err_text,
                                 vm_uuid=vm_uuid, vm_name=vm_name,
                                 command=subcmd)
            if vbe.is_not_found:
                raise VMNotFoundException(
                    identifier=vm_uuid or vm_name or "?",
                    vbox_error=vbe,
                )
            raise RuntimeError(
                f"VBoxManage error (rc={proc.returncode}): {err_text}"
            )

        return stdout

    # ─────────────────────────────────────────────────────────────────────────
    # UUID-first VM inventory
    # ─────────────────────────────────────────────────────────────────────────

    def list_all_vms(self) -> dict[str, str]:
        """
        Return every registered VM as {uuid: name}.

        Parses `VBoxManage list vms` output:
            "My VM Name" {550e8400-e29b-41d4-a716-446655440000}

        Returns empty dict if VBox is not installed or the command fails.
        """
        if not self.vbox_manage_cmd:
            return {}
        try:
            output = self.run_cmd(["list", "vms"], timeout=_T_FAST)
        except Exception as exc:
            logger.warning("list_all_vms failed: %s", exc)
            return {}

        result: dict[str, str] = {}
        # Pattern: "Name with spaces" {uuid}
        pattern = re.compile(r'^"(.+?)"\s+\{([0-9a-f-]+)\}', re.IGNORECASE)
        for line in output.splitlines():
            m = pattern.match(line.strip())
            if m:
                name, uuid = m.group(1), m.group(2).lower()
                result[uuid] = name
        logger.debug("list_all_vms: found %d VMs", len(result))
        return result

    def list_running_uuids(self) -> set[str]:
        """
        Return set of UUIDs for currently running VMs.
        Parses `VBoxManage list runningvms`.
        """
        if not self.vbox_manage_cmd:
            return set()
        try:
            output = self.run_cmd(["list", "runningvms"], timeout=_T_FAST)
        except Exception as exc:
            logger.warning("list_running_uuids failed: %s", exc)
            return set()

        uuids: set[str] = set()
        pattern = re.compile(r'^".*?"\s+\{([0-9a-f-]+)\}', re.IGNORECASE)
        for line in output.splitlines():
            m = pattern.match(line.strip())
            if m:
                uuids.add(m.group(1).lower())
        return uuids

    def list_running_names(self) -> set[str]:
        """
        Return set of VM *names* for currently running VMs.
        Preserved for backward compatibility with VMStatePoller.
        """
        if not self.vbox_manage_cmd:
            return set()
        try:
            output = self.run_cmd(["list", "runningvms"], timeout=_T_FAST)
        except Exception as exc:
            logger.warning("list_running_names failed: %s", exc)
            return set()

        names: set[str] = set()
        for line in output.splitlines():
            line = line.strip()
            if line.startswith('"'):
                try:
                    end = line.index('"', 1)
                    names.add(line[1:end])
                except ValueError:
                    pass
        return names

    # ─────────────────────────────────────────────────────────────────────────
    # Existence validation
    # ─────────────────────────────────────────────────────────────────────────

    def validate_vm(self, uuid: str) -> bool:
        """
        Return True if a VM with this UUID is registered in VirtualBox.
        Fast — uses the cached list_all_vms() parse; does NOT run showvminfo.
        """
        if not uuid:
            return False
        registered = self.list_all_vms()
        return uuid.lower() in registered

    def get_uuid_for_name(self, vm_name: str) -> Optional[str]:
        """
        Find the UUID for a VM name. Returns None if not found.
        Used to resolve legacy name-only records.
        """
        for uuid, name in self.list_all_vms().items():
            if name == vm_name:
                return uuid
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # State queries
    # ─────────────────────────────────────────────────────────────────────────

    def get_vm_state(self, vm_name: str) -> str:
        """
        Return 'running', 'stopped', or 'unknown' for a VM identified by name.
        Uses `list runningvms` — fast single call.
        Preserved for VMStatePoller backward compatibility.
        """
        try:
            running = self.list_running_names()
            return "running" if vm_name in running else "stopped"
        except Exception as exc:
            logger.warning("get_vm_state('%s') failed: %s", vm_name, exc)
            return "unknown"

    def get_vm_state_by_uuid(self, uuid: str) -> str:
        """
        Return 'running', 'stopped', or 'missing' for a VM identified by UUID.
        'missing' is returned if the UUID is not in the VBox registry at all.
        """
        all_vms  = self.list_all_vms()
        if uuid.lower() not in all_vms:
            return "missing"
        running  = self.list_running_uuids()
        return "running" if uuid.lower() in running else "stopped"

    # Alias used by legacy machines_db layer
    def get_live_status(self, vm_name: str) -> str:
        return self.get_vm_state(vm_name)

    def _get_detailed_state(self, identifier: str) -> str:
        """
        Use showvminfo to get detailed VMState (poweroff, starting, running, aborted, saved).
        """
        if not self.vbox_manage_cmd:
            return "unknown"
        try:
            # We use run_cmd directly with a short timeout to prevent locking up the loop.
            out = self.run_cmd(["showvminfo", identifier, "--machinereadable"], timeout=5)
            for line in out.splitlines():
                if line.startswith("VMState="):
                    return line.split("=", 1)[1].strip().strip('"')
        except Exception as exc:
            logger.debug("_get_detailed_state('%s') failed: %s", identifier, exc)
        return "unknown"

    # ─────────────────────────────────────────────────────────────────────────
    # VM creation helpers
    # ─────────────────────────────────────────────────────────────────────────

    def create_vm(self, vm_name: str, os_type: str = "Ubuntu_64",
                  base_folder=None):
        cmd = ["createvm", "--name", vm_name, "--ostype", os_type, "--register"]
        if base_folder:
            cmd += ["--basefolder", str(base_folder)]
        self.run_cmd(cmd)

    def set_vm_resources(self, vm_name: str, ram_mb: int, cpu_count: int):
        self.run_cmd([
            "modifyvm", vm_name,
            "--memory", str(ram_mb),
            "--cpus",   str(cpu_count),
        ])

    def configure_vm_display(self, vm_name: str):
        """
        Configures VM display rendering.
        Uses VMSVGA with 128 MB VRAM.
        3D acceleration is intentionally DISABLED — it causes VMs to abort
        on boot on many Windows host configurations (driver/WDDM mismatch).
        """
        self.run_cmd([
            "modifyvm", vm_name,
            "--vram", "128",
            "--graphicscontroller", "vmsvga",
            "--accelerate3d", "off",
        ])


    def create_disk(self, vm_name: str, disk_gb: int, disk_path):
        self.run_cmd([
            "createhd",
            "--filename", str(disk_path),
            "--size",     str(disk_gb * 1024),
            "--format",   "VDI",
        ])

    def attach_storage_controller(self, vm_name: str,
                                   name: str = "SATA",
                                   ctrl_type: str = "IntelAHCI"):
        self.run_cmd([
            "storagectl", vm_name,
            "--name",       name,
            "--add",        "sata",
            "--controller", ctrl_type,
        ])

    def attach_disk(self, vm_name: str, disk_path,
                    controller: str = "SATA", port: int = 0):
        self.run_cmd([
            "storageattach", vm_name,
            "--storagectl", controller,
            "--port",   str(port),
            "--device", "0",
            "--type",   "hdd",
            "--medium", str(disk_path),
        ])

    def attach_iso(self, vm_name: str, iso_path,
                   controller: str = "SATA", port: int = 1):
        self.run_cmd([
            "storageattach", vm_name,
            "--storagectl", controller,
            "--port",   str(port),
            "--device", "0",
            "--type",   "dvddrive",
            "--medium", str(iso_path),
        ])

    def detach_iso(self, vm_name: str,
                   controller: str = "SATA", port: int = 1):
        self.run_cmd([
            "storageattach", vm_name,
            "--storagectl", controller,
            "--port",   str(port),
            "--device", "0",
            "--type",   "dvddrive",
            "--medium", "emptydrive",
        ])

    def set_network_nat(self, vm_name: str):
        self.run_cmd(["modifyvm", vm_name, "--nic1", "nat"])

    def set_boot_order(self, vm_name: str,
                       boot1: str = "dvd",  boot2: str = "disk",
                       boot3: str = "none", boot4: str = "none"):
        self.run_cmd([
            "modifyvm", vm_name,
            "--boot1", boot1, "--boot2", boot2,
            "--boot3", boot3, "--boot4", boot4,
        ])

    # ─────────────────────────────────────────────────────────────────────────
    # VM lifecycle — UUID-first (preferred)
    # ─────────────────────────────────────────────────────────────────────────

    def start_vm_by_uuid(self, uuid: str, gui: bool = True,
                         skip_validation: bool = False):
        """
        Start a VM identified by UUID.

        Raises VMNotFoundException if the UUID is not in VBox registry.
        Discards saved/aborted state automatically before starting.

        Parameters
        ----------
        skip_validation : bool
            Set True when the caller has already validated the VM exists
            (e.g. VMService.start_vm) to avoid a redundant list vms call.
        """
        if not skip_validation and not self.validate_vm(uuid):
            raise VMNotFoundException(uuid)

        state = self.get_vm_state_by_uuid(uuid)
        logger.info("start_vm_by_uuid  uuid=%s  current_state=%s", uuid, state)

        if state in ("aborted", "saved"):
            logger.warning("uuid=%s is in '%s' state — discarding before start", uuid, state)
            self.run_cmd(["discardstate", uuid], vm_uuid=uuid)

        self._async_start_and_poll(uuid, gui)

    def _async_start_and_poll(self, identifier: str, gui: bool):
        """
        Fire VBoxManage startvm --type separate, wait for it to exit, then poll
        showvminfo until VMState == 'running', an explicit failure state is
        detected, or the timeout elapses.

        Why --type separate?
        --------------------
        --type gui     : VBoxManage stays alive managing the session → blocks
                         communicate() for the full VM boot (often >20 s)
                         causing a false timeout failure.
        --type separate: VBoxManage spawns the VM as an independent OS process
                         and exits in ~1-3 s. The VM window still appears
                         (allowing Win32 embedding). This is the correct mode
                         for embedding-based consoles.
        --type headless: Used only when gui=False (no window needed).

        Failure states detected early
        ------------------------------
        - startvm exits with rc != 0         → raise immediately with stderr
        - VMState == 'aborted'               → VBox rejected the start
        - VMState stays 'poweroff' for >15s  → start silently failed
        """
        self._require_vbox()
        # 'separate' exits quickly AND produces an embeddable window.
        # Fall back to 'headless' only when explicitly requested (no GUI).
        vbox_type = "headless" if not gui else "separate"
        cmd = [
            self.vbox_manage_cmd, "startvm", identifier,
            "--type", vbox_type,
        ]
        logger.info("START  cmd: %s", " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=_NO_WINDOW,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to launch VBoxManage startvm for '{identifier}': {exc}"
            ) from exc

        # ── Wait for the startvm *process* to exit ───────────────────────
        # With --type separate, VBoxManage exits in ~1-3 s after spawning
        # the VM process. 30 s timeout is a conservative safety net for
        # very slow machines (high disk I/O, first boot, antivirus scan).
        try:
            stdout_out, stderr_out = proc.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise RuntimeError(
                f"VBoxManage startvm did not exit within 30 s for '{identifier}'.\n"
                "This is unexpected with --type separate. VirtualBox may be\n"
                "locked, frozen, or the VM disk has a serious error."
            )

        if proc.returncode != 0:
            err_text = stderr_out.strip()
            logger.error(
                "startvm rc=%d for '%s':\n%s",
                proc.returncode, identifier, err_text,
            )
            vbe = classify_error(err_text, vm_uuid=identifier, command="startvm")
            if vbe.is_not_found:
                raise VMNotFoundException(identifier, vbox_error=vbe)
            raise RuntimeError(
                f"VBoxManage startvm failed (rc={proc.returncode}):\n{err_text}"
            )

        logger.info(
            "startvm process exited rc=0 for '%s' — polling for 'running' state…",
            identifier,
        )

        # ── Poll showvminfo until 'running', failure state, or timeout ───
        # 120 s covers slow first-boot scenarios (BIOS POST, large disk,
        # antivirus I/O contention). Poll every 1 s so we react quickly.
        timeout_s      = 120.0
        t0             = time.monotonic()
        last_state     = "unknown"
        poweroff_ticks = 0
        POWEROFF_LIMIT = 15     # 15 × 1 s = 15 s grace before declaring stuck

        while time.monotonic() - t0 < timeout_s:
            state = self._get_detailed_state(identifier)

            if state != last_state:
                logger.info(
                    "VM '%s' state: %s → %s  (%.1fs elapsed)",
                    identifier, last_state, state, time.monotonic() - t0,
                )
                last_state     = state
                poweroff_ticks = 0

            # ── Success ──────────────────────────────────────────────────
            if state == "running":
                logger.info(
                    "VM '%s' reached 'running' in %.1f s.",
                    identifier, time.monotonic() - t0,
                )
                return

            # ── Hard failure: VBox explicitly aborted the VM ─────────────
            if state == "aborted":
                raise RuntimeError(
                    f"VM '{identifier}' was aborted by VirtualBox during startup.\n"
                    "Common causes: 3D acceleration driver mismatch, insufficient RAM,\n"
                    "or a corrupt disk image. Check VirtualBox logs for details."
                )

            # ── Soft failure: stuck at 'poweroff' despite rc=0 ───────────
            # A fresh boot briefly stays 'poweroff' before transitioning.
            # Only raise if it persists far longer than expected.
            if state == "poweroff":
                poweroff_ticks += 1
                if poweroff_ticks >= POWEROFF_LIMIT:
                    raise RuntimeError(
                        f"VM '{identifier}' did not leave 'poweroff' state after "
                        f"{POWEROFF_LIMIT}s.\n"
                        "VirtualBox may have silently rejected the start request.\n"
                        "Common causes: VBox session lock, insufficient host RAM, "
                        "or a missing display driver."
                    )
            else:
                poweroff_ticks = 0

            time.sleep(1.0)

        raise RuntimeError(
            f"Timeout ({timeout_s:.0f}s) waiting for VM '{identifier}' to reach "
            f"'running' state. Final detected state: '{last_state}'.\n"
            "The VM may still be booting — check My Machines page for live status."
        )

    @_retry_on_lock(retries=3, delay=0.6)
    def stop_vm_by_uuid(self, uuid: str, force: bool = False):
        """
        Stop a VM identified by UUID.
        Uses graceful ACPI shutdown unless force=True (poweroff).

        Raises VMNotFoundException if the UUID is not in VBox registry.
        """
        if not self.validate_vm(uuid):
            raise VMNotFoundException(uuid)

        logger.info("stop_vm_by_uuid  uuid=%s  force=%s", uuid, force)
        if force:
            self._poweroff_by_uuid(uuid)
        else:
            try:
                self.run_cmd(
                    ["controlvm", uuid, "acpipowerbutton"],
                    timeout=_T_STOP, vm_uuid=uuid,
                )
            except VMNotFoundException:
                raise
            except Exception as exc:
                logger.warning(
                    "ACPI shutdown failed for uuid=%s (%s), falling back to poweroff",
                    uuid, exc,
                )
                self._poweroff_by_uuid(uuid)

    def delete_vm_by_uuid(self, uuid: str):
        """
        Unregister and delete a VM (including disk images) by UUID.

        Raises VMNotFoundException if the UUID is not in VBox registry.
        """
        if not self.validate_vm(uuid):
            raise VMNotFoundException(uuid)

        logger.info("delete_vm_by_uuid  uuid=%s", uuid)
        self.run_cmd(
            ["unregistervm", uuid, "--delete"],
            timeout=30, vm_uuid=uuid,
        )

    @_retry_on_lock(retries=3, delay=0.6)
    def _poweroff_by_uuid(self, uuid: str):
        try:
            self.run_cmd(
                ["controlvm", uuid, "poweroff"],
                timeout=_T_STOP, vm_uuid=uuid,
            )
        except Exception:
            pass   # Already off

    # ─────────────────────────────────────────────────────────────────────────
    # VM lifecycle — name-based (legacy, preserved for backward compat)
    # ─────────────────────────────────────────────────────────────────────────

    def discard_saved_state(self, vm_name: str):
        self.run_cmd(["discardstate", vm_name])

    def start_vm(self, vm_name: str, gui: bool = True,
                 cached_state: str = None):
        """
        Start a VM by name (legacy path — preferred: start_vm_by_uuid).

        cached_state: if provided by VMStatePoller, the blocking
                      get_vm_state() call is skipped.
        """
        state = (
            cached_state
            if cached_state is not None
            else self.get_vm_state(vm_name)
        )
        logger.info("start_vm '%s'  state=%s", vm_name, state)

        if state in ("aborted", "saved"):
            logger.warning("'%s' in '%s' — discarding state first", vm_name, state)
            self.discard_saved_state(vm_name)

        self._async_start_and_poll(vm_name, gui)

    def stop_vm(self, vm_name: str):
        """Graceful ACPI shutdown — falls back to poweroff on failure."""
        try:
            self.run_cmd(["controlvm", vm_name, "acpipowerbutton"],
                         timeout=_T_STOP)
        except Exception as exc:
            logger.warning("stop_vm ACPI failed (%s), using poweroff", exc)
            self.poweroff_vm(vm_name)

    def poweroff_vm(self, vm_name: str):
        try:
            self.run_cmd(["controlvm", vm_name, "poweroff"], timeout=_T_STOP)
        except Exception:
            pass  # already off

    def delete_vm(self, vm_name: str):
        try:
            self.run_cmd(["unregistervm", vm_name, "--delete"], timeout=30)
        except VMNotFoundException:
            logger.warning("delete_vm '%s': already absent from VBox", vm_name)
        except Exception as exc:
            logger.error("delete_vm '%s': %s", vm_name, exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Snapshot management
    # ─────────────────────────────────────────────────────────────────────────

    def take_snapshot(self, vm_name: str, snapshot_name: str,
                      description: str = "", live: bool = False,
                      cached_state: str = None):
        """
        Take a VM snapshot (name-based, for backward compat).

        Flag selection by state:
          running + live=True  → --live   (hotshot)
          running + live=False → --pause  (freeze → snap → resume)
          stopped / paused     → (no flag)

        Timeout: 6 minutes for large live snapshots.
        """
        state = (
            cached_state
            if cached_state is not None
            else self.get_vm_state(vm_name)
        )
        logger.info(
            "take_snapshot  vm='%s'  name='%s'  state=%s  live=%s",
            vm_name, snapshot_name, state, live,
        )
        cmd = ["snapshot", vm_name, "take", snapshot_name]
        if description:
            cmd += ["--description", description]
        if state == "running":
            cmd += ["--live"] if live else ["--pause"]

        self.run_cmd(cmd, timeout=_T_SNAP)
        logger.info("Snapshot '%s' complete for '%s'", snapshot_name, vm_name)

    def restore_snapshot(self, vm_name: str, snapshot_name: str,
                         cached_state: str = None):
        """Power off if running, then restore to named snapshot."""
        state = (
            cached_state
            if cached_state is not None
            else self.get_vm_state(vm_name)
        )
        if state == "running":
            logger.info("Powering off '%s' before restore…", vm_name)
            self.poweroff_vm(vm_name)
            time.sleep(2)

        self.run_cmd(["snapshot", vm_name, "restore", snapshot_name],
                     timeout=60)
        logger.info("Restored '%s' → '%s'", vm_name, snapshot_name)

    def delete_snapshot(self, vm_name: str, snapshot_name: str):
        """
        Delete a snapshot (merges disk delta into parent).
        Pre-validates VM existence; raises VMNotFoundException if missing.
        """
        # Validate first — never call VBox for a ghost VM
        uuid = self.get_uuid_for_name(vm_name)
        if uuid is not None and not self.validate_vm(uuid):
            raise VMNotFoundException(vm_name)

        self.run_cmd(
            ["snapshot", vm_name, "delete", snapshot_name],
            timeout=180,
        )
        logger.info("Deleted snapshot '%s' from '%s'", snapshot_name, vm_name)

    def list_snapshots(self, vm_name: str) -> list:
        """
        Return list of dicts {name, uuid} from `snapshot list --machinereadable`.
        Returns [] if the VM has no snapshots or on any error.
        """
        try:
            output = self.run_cmd(
                ["snapshot", vm_name, "list", "--machinereadable"]
            )
        except Exception as exc:
            logger.debug("list_snapshots('%s'): %s", vm_name, exc)
            return []

        snapshots: list = []
        cur: dict       = {}
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("SnapshotName="):
                if cur:
                    snapshots.append(cur)
                cur = {
                    "name": line.split("=", 1)[1].strip().strip('"'),
                    "uuid": "",
                }
            elif line.startswith("SnapshotUUID=") and cur:
                cur["uuid"] = line.split("=", 1)[1].strip().strip('"')
        if cur:
            snapshots.append(cur)
        return snapshots

    def export_vm(self, vm_name: str, output_path: str):
        """Export VM as OVA. Can be very slow for large VMs."""
        self.run_cmd(
            ["export", vm_name, "--output", str(output_path)],
            timeout=_T_EXPORT,
        )
        logger.info("Exported '%s' → %s", vm_name, output_path)
