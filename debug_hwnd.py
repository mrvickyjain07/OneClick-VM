"""
debug_hwnd.py
Run this WHILE a VirtualBox VM is running to verify window detection.

Usage:
  cd "d:\AddingUI\Antigravity - Copy\OneClickVM"
  python debug_hwnd.py [vm_name]

If vm_name is omitted, lists ALL visible windows with their HWNDs.
"""
import sys, ctypes, ctypes.wintypes, time

WNDENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.wintypes.BOOL,
    ctypes.wintypes.HWND,
    ctypes.wintypes.LPARAM,
)
user32 = ctypes.windll.user32

def list_all_windows():
    results = []
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        results.append((hwnd, buf.value))
        return True
    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return results


def main():
    vm_name = sys.argv[1] if len(sys.argv) > 1 else ""

    print("=" * 70)
    print("OneClickVM — HWND Debug Tool")
    print("=" * 70)

    wins = list_all_windows()
    print(f"\nTotal visible top-level windows: {len(wins)}\n")

    if not vm_name:
        print("All visible windows:")
        for hwnd, title in sorted(wins, key=lambda x: x[1].lower()):
            print(f"  0x{hwnd:08X}  {title}")
        print("\nRe-run with a VM name to test matching:")
        print("  python debug_hwnd.py MyVM")
        return

    print(f"Looking for VM window matching: '{vm_name}'")
    print()

    norm = vm_name.lower().replace("_", " ").replace("-", " ").strip()
    matched = []
    vbox_any = []

    for hwnd, title in wins:
        t = title.lower()
        if norm in t.replace("_", " ").replace("-", " "):
            matched.append((hwnd, title))
        elif "virtualbox" in t and "manager" not in t:
            vbox_any.append((hwnd, title))

    if matched:
        print(f"✅ MATCHED ({len(matched)} window(s)):")
        for hwnd, title in matched:
            print(f"   HWND=0x{hwnd:08X}  '{title}'")
        best = matched[0][0]
    elif vbox_any:
        print(f"⚠  No direct match. VirtualBox window(s) found as fallback:")
        for hwnd, title in vbox_any:
            print(f"   HWND=0x{hwnd:08X}  '{title}'")
        best = vbox_any[0][0]
    else:
        print("❌ No VirtualBox VM window found.")
        print("   Make sure the VM is running with --type gui")
        return

    print()
    hwnd = best
    print(f"Best HWND: 0x{hwnd:08X}")

    # Read current window style
    GWL_STYLE = -16
    style = user32.GetWindowLongW(hwnd, GWL_STYLE)
    print(f"Current WS style: 0x{style:08X}")

    WS_CAPTION    = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_CHILD      = 0x40000000

    has_caption    = bool(style & WS_CAPTION)
    has_thickframe = bool(style & WS_THICKFRAME)
    is_child       = bool(style & WS_CHILD)

    print(f"  WS_CAPTION    present: {has_caption}")
    print(f"  WS_THICKFRAME present: {has_thickframe}")
    print(f"  WS_CHILD      present: {is_child}")
    print()

    if is_child:
        print("ℹ️  Window is already a child (embedded in another window).")
    else:
        print("✅ Window is a top-level window (ready to embed).")

    print()
    print("Now testing backend import chain…")
    sys.path.insert(0, ".")
    try:
        from backend.vm_console_service import (
            find_vm_window, poll_for_vm_window,
            reparent_and_strip, move_embedded_window, detach_window,
            strip_window_decorations,
        )
        print("✅ backend.vm_console_service — all exports OK")
    except Exception as e:
        print(f"❌ backend.vm_console_service import failed: {e}")
        return

    found = find_vm_window(vm_name)
    if found:
        print(f"✅ find_vm_window('{vm_name}') → HWND=0x{found:08X}")
    else:
        print(f"❌ find_vm_window('{vm_name}') → None")

    print()
    print("Debug complete. If HWND was found, embedding should work.")
    print("Restart the app and launch a VM to see it embedded in the Console.")


if __name__ == "__main__":
    main()
