"""Read-only sampling of the owned browser PID; no titles, text, or input."""
import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys
import time

pid, stop_file, output = int(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
user = C.WinDLL("user32", use_last_error=True)
callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
user.GetForegroundWindow.restype = W.HWND
user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
user.IsWindowVisible.argtypes = [W.HWND]
user.EnumWindows.argtypes = [callback, W.LPARAM]
report = {"samples": 0, "foreground_target_hits": 0, "visible_target_window_hits": 0,
          "foreground_available_samples": 0, "cursor_changes": 0}
previous = None
def owned(hwnd):
    actual = W.DWORD()
    user.GetWindowThreadProcessId(hwnd, C.byref(actual))
    return actual.value == pid
@callback
def visit(hwnd, _):
    if user.IsWindowVisible(hwnd) and owned(hwnd):
        report["visible_target_window_hits"] += 1
    return True
deadline = time.monotonic() + 45
while not stop_file.exists() and time.monotonic() < deadline:
    front = user.GetForegroundWindow()
    report["samples"] += 1
    report["foreground_available_samples"] += bool(front)
    report["foreground_target_hits"] += bool(front) and owned(front)
    user.EnumWindows(visit, 0)
    point = W.POINT()
    user.GetCursorPos(C.byref(point))
    current = (point.x, point.y)
    report["cursor_changes"] += previous is not None and previous != current
    previous = current
    time.sleep(0.01)
report["scope"] = "owned browser main PID only; sampled not continuous; cursor changes have no attribution"
output.write_text(json.dumps(report, indent=2), encoding="utf8")
