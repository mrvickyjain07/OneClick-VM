"""
backend/vm_console_service.py
Win32 window-finding and embedding helpers for the Console viewport.

Embedding contract
------------------
1. Find HWND by scanning VirtualBox window titles (with fuzzy normalisation).
2. SetParent(vm_hwnd, container_hwnd)  ← must come FIRST.
3. Strip WS_CAPTION / WS_THICKFRAME, add WS_CHILD | WS_CLIPSIBLINGS | WS_CLIPCHILDREN.
4. SetWindowPos with SWP_FRAMECHANGED | SWP_SHOWWINDOW to flush the style change
   and resize to fill the container.
5. ShowWindow(SW_SHOW) + UpdateWindow to force a repaint.
6. On every QResizeEvent call move_embedded_window() which re-issues MoveWindow.

On detach:
  restore WS_OVERLAPPEDWINDOW, remove WS_CHILD, SetParent(hwnd, NULL).

Windows-only — all functions return gracefully on other platforms.
"""
import sys
import time
from .logger import get_logger

logger = get_logger("VMConsoleService")

_IS_WINDOWS = sys.platform.startswith("win")

if _IS_WINDOWS:
    import ctypes
    import ctypes.wintypes as wintypes

    _u32 = ctypes.windll.user32

    # ── Style constants ────────────────────────────────────────────────────
    GWL_STYLE   = -16
    GWL_EXSTYLE = -20

    # Bits to ADD (child embedding)
    WS_CHILD         = 0x40000000
    WS_VISIBLE       = 0x10000000
    WS_CLIPCHILDREN  = 0x02000000
    WS_CLIPSIBLINGS  = 0x04000000

    # Bits to STRIP (decoration removal)
    WS_CAPTION     = 0x00C00000   # title bar (= WS_BORDER | WS_DLGFRAME)
    WS_THICKFRAME  = 0x00040000   # resize border
    WS_SYSMENU     = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    WS_BORDER      = 0x00800000

    _STRIP_MASK = (WS_CAPTION | WS_THICKFRAME | WS_SYSMENU |
                   WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_BORDER)

    # SetWindowPos flags
    SWP_NOZORDER     = 0x0004
    SWP_NOACTIVATE   = 0x0010
    SWP_FRAMECHANGED = 0x0020
    SWP_SHOWWINDOW   = 0x0040

    # ShowWindow commands
    SW_SHOW      = 5
    SW_SHOWNA    = 8   # show without activating

    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )


# ── Title normalisation ────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return s.lower().replace("_", " ").replace("-", " ").strip()


# ── Window enumeration ────────────────────────────────────────────────────────

def find_vm_window(vm_name: str) -> "int | None":
    """
    Enumerate all visible top-level windows and return the HWND of the
    VirtualBox VM window for vm_name.

    VirtualBox window title patterns:
        "<vm_name> [Running] - Oracle VirtualBox"
        "<vm_name> - Oracle VirtualBox"
    """
    if not _IS_WINDOWS:
        return None

    norm_vm = _norm(vm_name)
    primary  = []   # matched by vm_name AND "virtualbox"
    secondary = []  # matched by vm_name only
    fallback  = []  # any non-Manager VirtualBox window

    def _cb(hwnd, _lp):
        if not _u32.IsWindowVisible(hwnd):
            return True
        length = _u32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _u32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        nt    = _norm(title)

        if norm_vm in nt:
            if "virtualbox" in nt:
                primary.append((hwnd, title))
            else:
                secondary.append((hwnd, title))
        elif "virtualbox" in nt and "manager" not in nt and "preferences" not in nt:
            fallback.append((hwnd, title))
        return True

    _u32.EnumWindows(WNDENUMPROC(_cb), 0)

    for lst in (primary, secondary, fallback):
        if lst:
            hwnd, title = lst[0]
            logger.info(f"Found VM window  HWND=0x{hwnd:08X}  '{title}'")
            return hwnd

    return None


def poll_for_vm_window(vm_name: str,
                       timeout_s: int   = 60,
                       interval_s: float = 0.5) -> "int | None":
    """
    Blocking poll for the VirtualBox window — must run in a QThread.
    Returns the HWND when found, or None on timeout.
    """
    deadline = time.time() + timeout_s
    tick = 0
    while time.time() < deadline:
        hwnd = find_vm_window(vm_name)
        if hwnd:
            time.sleep(0.4)   # let VBox finish painting its first frame
            return hwnd
        tick += 1
        if tick % 10 == 0:
            logger.debug(f"Waiting for '{vm_name}' window… "
                         f"{int(time.time()-(deadline-timeout_s))}s elapsed")
        time.sleep(interval_s)
    logger.warning(f"Timed out waiting for '{vm_name}' after {timeout_s}s")
    return None


# ── Core embedding ────────────────────────────────────────────────────────────

def reparent_and_strip(hwnd: int, parent_hwnd: int,
                        x: int, y: int, w: int, h: int):
    """
    Full embedding sequence — call once when HWND is first found.

    Order is critical:
      1. SetParent  (must happen before style changes)
      2. SetWindowLong  (strip decorations, add WS_CHILD)
      3. SetWindowPos   (flush frame change + resize)
      4. ShowWindow / UpdateWindow  (force repaint)
    """
    if not _IS_WINDOWS:
        return

    logger.debug(
        f"reparent_and_strip  hwnd=0x{hwnd:08X}  "
        f"parent=0x{parent_hwnd:08X}  ({x},{y}) {w}×{h}"
    )

    try:
        # ── 1. Re-parent ──────────────────────────────────────────────────
        _u32.SetParent(hwnd, parent_hwnd)

        # ── 2. Strip decorations, inject child bits ────────────────────────
        style = _u32.GetWindowLongW(hwnd, GWL_STYLE)
        logger.debug(f"  original style = 0x{style:08X}")
        new_style = ((style & ~_STRIP_MASK)
                     | WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN | WS_CLIPSIBLINGS)
        _u32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
        logger.debug(f"  new style      = 0x{new_style:08X}")

        # ── 3. Resize + frame-change notification ─────────────────────────
        _u32.SetWindowPos(
            hwnd, None,
            x, y, w, h,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        )

        # ── 4. Explicit show + repaint ────────────────────────────────────
        _u32.ShowWindow(hwnd, SW_SHOW)
        _u32.UpdateWindow(hwnd)
        _u32.InvalidateRect(hwnd, None, True)

        logger.info(
            f"Embedded 0x{hwnd:08X} into 0x{parent_hwnd:08X}  {w}×{h}"
        )

    except Exception as e:
        logger.error(f"reparent_and_strip failed: {e}")
        raise


def move_embedded_window(hwnd: int, x: int, y: int, w: int, h: int):
    """
    Resize/reposition an already-embedded VM window.
    Called from VMViewport continuous timer and resizeEvent.
    """
    if not _IS_WINDOWS or not hwnd:
        return
    try:
        # Enforce continuous position without z-order changes
        _u32.SetWindowPos(hwnd, None, x, y, w, h, SWP_NOZORDER)
        _u32.UpdateWindow(hwnd)
    except Exception as e:
        logger.warning(f"move_embedded_window: {e}")

def is_window_valid_and_visible(hwnd: int) -> bool:
    if not _IS_WINDOWS or not hwnd:
        return False
    return bool(_u32.IsWindow(hwnd) and _u32.IsWindowVisible(hwnd))

def get_window_size(hwnd: int):
    if not _IS_WINDOWS or not hwnd:
        return (0, 0)
    rect = wintypes.RECT()
    _u32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.right - rect.left, rect.bottom - rect.top)


def detach_window(hwnd: int):
    """
    Restore the native window to a free-floating state.
    The VM keeps running — the VirtualBox window just becomes a normal
    top-level window again.
    """
    if not _IS_WINDOWS or not hwnd:
        return
    try:
        WS_OVERLAPPEDWINDOW = 0x00CF0000
        style = _u32.GetWindowLongW(hwnd, GWL_STYLE)
        new_style = ((style & ~(WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS))
                     | WS_OVERLAPPEDWINDOW | WS_VISIBLE)
        _u32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
        _u32.SetParent(hwnd, None)
        _u32.SetWindowPos(
            hwnd, None, 80, 80, 1024, 768,
            SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        )
        _u32.ShowWindow(hwnd, SW_SHOW)
        logger.info(f"Detached 0x{hwnd:08X} — VM continues in its own window.")
    except Exception as e:
        logger.warning(f"detach_window: {e}")


# ── Legacy shim ───────────────────────────────────────────────────────────────

def strip_window_decorations(hwnd: int):
    """Compatibility shim. Prefer reparent_and_strip() for full embedding."""
    if not _IS_WINDOWS:
        return
    try:
        style = _u32.GetWindowLongW(hwnd, GWL_STYLE)
        _u32.SetWindowLongW(hwnd, GWL_STYLE, style & ~_STRIP_MASK)
        _u32.SetWindowPos(hwnd, None, 0, 0, 0, 0,
                          0x0001 | 0x0002 | SWP_NOZORDER | SWP_FRAMECHANGED)
    except Exception as e:
        logger.error(f"strip_window_decorations: {e}")
