"""
backend/vm_session_manager.py
Tracks the currently active console session — which VM is attached and its state.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from .logger import get_logger

logger = get_logger("VMSessionManager")


class ConsoleState(str, Enum):
    IDLE         = "idle"
    CONNECTING   = "connecting"
    CONNECTED    = "connected"
    DISCONNECTED = "disconnected"
    ERROR        = "error"


@dataclass
class ConsoleSession:
    vm_name: str
    hwnd:    Optional[int]   = None
    state:   ConsoleState    = ConsoleState.CONNECTING
    error:   str             = ""


class VMSessionManager:
    """
    Singleton-style manager: only one console session at a time.
    """
    def __init__(self):
        self._session: Optional[ConsoleSession] = None

    # ── Public API ────────────────────────────────────────────────────────

    def begin(self, vm_name: str) -> ConsoleSession:
        """Start a new console session for vm_name."""
        self._session = ConsoleSession(vm_name=vm_name, state=ConsoleState.CONNECTING)
        logger.info(f"Console session started for '{vm_name}'")
        return self._session

    def attach(self, hwnd: int):
        """Mark the session as connected once the window handle is found."""
        if self._session:
            self._session.hwnd  = hwnd
            self._session.state = ConsoleState.CONNECTED
            logger.info(f"Console attached to HWND={hwnd}")

    def disconnect(self):
        """Cleanly end the active session."""
        if self._session:
            logger.info(f"Console session ended for '{self._session.vm_name}'")
            self._session.state = ConsoleState.DISCONNECTED
            self._session = None

    def fail(self, reason: str):
        if self._session:
            self._session.state = ConsoleState.ERROR
            self._session.error = reason
            logger.error(f"Console error: {reason}")

    @property
    def session(self) -> Optional[ConsoleSession]:
        return self._session

    @property
    def active_vm(self) -> Optional[str]:
        return self._session.vm_name if self._session else None

    @property
    def is_connected(self) -> bool:
        return (
            self._session is not None
            and self._session.state == ConsoleState.CONNECTED
        )
