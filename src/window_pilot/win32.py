"""Narrow Win32 boundary. No desktop DC reads, UIA, global input or activation."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time
import zlib
from dataclasses import asdict, dataclass

if sys.platform != "win32":
    raise RuntimeError("Window Pilot requires an interactive Windows desktop")

U = C.WinDLL("user32", use_last_error=True)
G = C.WinDLL("gdi32", use_last_error=True)
K = C.WinDLL("kernel32", use_last_error=True)


def api(dll, name, result, *args):
    fn = getattr(dll, name)
    fn.restype, fn.argtypes = result, list(args)
    return fn


PTR = C.c_void_p
CALLBACK = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


api(U, "IsWindow", W.BOOL, W.HWND)
api(U, "IsWindowVisible", W.BOOL, W.HWND)
api(U, "IsWindowEnabled", W.BOOL, W.HWND)
api(U, "IsIconic", W.BOOL, W.HWND)
api(U, "GetForegroundWindow", W.HWND)
api(U, "GetCursorPos", W.BOOL, C.POINTER(W.POINT))
api(U, "GetWindowThreadProcessId", W.DWORD, W.HWND, C.POINTER(W.DWORD))
api(U, "GetWindowTextW", C.c_int, W.HWND, W.LPWSTR, C.c_int)
api(U, "GetClassNameW", C.c_int, W.HWND, W.LPWSTR, C.c_int)
api(U, "GetClientRect", W.BOOL, W.HWND, C.POINTER(W.RECT))
api(U, "ClientToScreen", W.BOOL, W.HWND, C.POINTER(W.POINT))
api(U, "ScreenToClient", W.BOOL, W.HWND, C.POINTER(W.POINT))
api(U, "EnumWindows", W.BOOL, CALLBACK, W.LPARAM)
api(U, "PostMessageW", W.BOOL, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
api(U, "SendMessageTimeoutW", W.LPARAM, W.HWND, W.UINT, W.WPARAM,
    W.LPARAM, W.UINT, W.UINT, C.POINTER(C.c_size_t))
api(U, "PrintWindow", W.BOOL, W.HWND, W.HDC, W.UINT)
api(U, "ChildWindowFromPointEx", W.HWND, W.HWND, W.POINT, W.UINT)
api(U, "GetAncestor", W.HWND, W.HWND, W.UINT)
api(U, "GetDesktopWindow", W.HWND)
api(U, "GetShellWindow", W.HWND)
window_long = api(U, "GetWindowLongPtrW" if C.sizeof(PTR) == 8 else "GetWindowLongW", C.c_ssize_t, W.HWND, C.c_int)
api(U, "SetProcessDpiAwarenessContext", W.BOOL, PTR)
api(G, "CreateCompatibleDC", W.HDC, W.HDC)
api(G, "CreateDIBSection", W.HBITMAP, W.HDC, PTR, W.UINT, C.POINTER(PTR), PTR, W.DWORD)
api(G, "SelectObject", W.HANDLE, W.HDC, W.HANDLE)
api(G, "DeleteObject", W.BOOL, W.HANDLE)
api(G, "DeleteDC", W.BOOL, W.HDC)
api(K, "OpenProcess", W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
api(K, "CloseHandle", W.BOOL, W.HANDLE)
api(K, "GetProcessTimes", W.BOOL, W.HANDLE, *([C.POINTER(W.FILETIME)] * 4))
api(K, "QueryFullProcessImageNameW", W.BOOL, W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD))
U.SetProcessDpiAwarenessContext(PTR(-4))  # PMv2; no logical-coordinate scaling


class PilotError(RuntimeError):
    pass


def check(ok, operation):
    if not ok:
        raise PilotError(f"{operation}: Win32 error {C.get_last_error()}")
    return ok


def canonical(path):
    return os.path.normcase(os.path.realpath(path))


@dataclass(frozen=True)
class Identity:
    hwnd: int
    pid: int
    created: int
    exe: str
    tid: int
    klass: str


def process_identity(pid):
    handle = check(K.OpenProcess(0x1000, False, pid), "OpenProcess")
    try:
        created, exited, kernel, user = (W.FILETIME() for _ in range(4))
        check(K.GetProcessTimes(handle, C.byref(created), C.byref(exited),
                                C.byref(kernel), C.byref(user)), "GetProcessTimes")
        name, size = C.create_unicode_buffer(32768), W.DWORD(32768)
        check(K.QueryFullProcessImageNameW(handle, 0, name, C.byref(size)), "process image")
        return ((created.dwHighDateTime << 32) | created.dwLowDateTime, canonical(name.value))
    finally:
        K.CloseHandle(handle)


def input_integrity(pid):
    """Read token integrity; this never changes privileges or message filters."""
    advapi = C.WinDLL("advapi32", use_last_error=True)
    open_token = api(advapi, "OpenProcessToken", W.BOOL, W.HANDLE, W.DWORD, C.POINTER(W.HANDLE))
    get_info = api(advapi, "GetTokenInformation", W.BOOL, W.HANDLE, C.c_int, PTR, W.DWORD, C.POINTER(W.DWORD))
    count = api(advapi, "GetSidSubAuthorityCount", C.POINTER(C.c_ubyte), PTR)
    authority = api(advapi, "GetSidSubAuthority", C.POINTER(W.DWORD), PTR, W.DWORD)
    process = check(K.OpenProcess(0x1000, False, pid), "OpenProcess/integrity")
    token = W.HANDLE()
    try:
        check(open_token(process, 0x0008, C.byref(token)), "OpenProcessToken/query")
        length = W.DWORD()
        get_info(token, 25, None, 0, C.byref(length))  # TokenIntegrityLevel
        if not length.value or length.value > 65536:
            raise PilotError("INPUT_INTEGRITY_UNKNOWN")
        buffer = C.create_string_buffer(length.value)
        check(get_info(token, 25, buffer, length, C.byref(length)), "TokenIntegrityLevel")
        sid = C.cast(buffer, C.POINTER(PTR))[0]  # TOKEN_MANDATORY_LABEL.Label.Sid
        sub_count = count(sid)[0]
        if not sub_count:
            raise PilotError("INPUT_INTEGRITY_UNKNOWN")
        return authority(sid, sub_count - 1)[0]
    finally:
        if token.value:
            K.CloseHandle(token)
        K.CloseHandle(process)


def input_access(target):
    verify(target)
    sender, receiver = input_integrity(os.getpid()), input_integrity(target.pid)
    return {"sender_rid": sender, "target_rid": receiver,
            "blocked_by_integrity": receiver > sender,
            "meaning": "preflight_only_PostMessage_and_visual_effect_still_required"}


def process_scope(pid):
    """Match user SID/session across ordinary MCP and elevated worker (query only)."""
    advapi = C.WinDLL("advapi32", use_last_error=True)
    open_token = api(advapi, "OpenProcessToken", W.BOOL, W.HANDLE, W.DWORD, C.POINTER(W.HANDLE))
    get_info = api(advapi, "GetTokenInformation", W.BOOL, W.HANDLE, C.c_int, PTR, W.DWORD, C.POINTER(W.DWORD))
    sid_length = api(advapi, "GetLengthSid", W.DWORD, PTR)
    get_session = api(K, "ProcessIdToSessionId", W.BOOL, W.DWORD, C.POINTER(W.DWORD))
    process = check(K.OpenProcess(0x1000, False, pid), "OpenProcess/scope")
    token = W.HANDLE()
    try:
        check(open_token(process, 0x0008, C.byref(token)), "OpenProcessToken/scope")
        length = W.DWORD()
        get_info(token, 1, None, 0, C.byref(length))  # TokenUser
        if not 0 < length.value <= 65536:
            raise PilotError("PROCESS_USER_UNKNOWN")
        buffer = C.create_string_buffer(length.value)
        check(get_info(token, 1, buffer, length, C.byref(length)), "TokenUser")
        sid = C.cast(buffer, C.POINTER(PTR))[0]
        size = sid_length(sid)
        if not 0 < size <= 1024:
            raise PilotError("PROCESS_USER_UNKNOWN")
        session = W.DWORD()
        check(get_session(pid, C.byref(session)), "ProcessIdToSessionId")
        convert_sid = api(advapi, "ConvertSidToStringSidW", W.BOOL, PTR, C.POINTER(PTR))
        free = api(K, "LocalFree", PTR, PTR)
        sid_text = PTR()
        check(convert_sid(sid, C.byref(sid_text)), "user SID")
        try:
            value = C.wstring_at(sid_text)
        finally:
            free(sid_text)
        return {"user_sid_digest": hashlib.sha256(C.string_at(sid, size)).hexdigest(), "sid": value, "session": session.value}
    finally:
        if token.value:
            K.CloseHandle(token)
        K.CloseHandle(process)


def text(hwnd, class_name=False):
    buf = C.create_unicode_buffer(2048)
    (U.GetClassNameW if class_name else U.GetWindowTextW)(hwnd, buf, len(buf))
    return buf.value


def identity(hwnd):
    if type(hwnd) is not int or hwnd in (0, 0xffff) or not U.IsWindow(hwnd):
        raise PilotError("INVALID_WINDOW: a live exact HWND is required")
    pid = W.DWORD()
    tid = U.GetWindowThreadProcessId(hwnd, C.byref(pid))
    created, exe = process_identity(pid.value)
    return Identity(hwnd, pid.value, created, exe, tid, text(hwnd, True))


def verify(target):
    if identity(target.hwnd) != target:
        raise PilotError("STALE_WINDOW: HWND/process identity changed; bind again")
    if not U.IsWindowVisible(target.hwnd) or U.IsIconic(target.hwnd):
        raise PilotError("UNAVAILABLE_WINDOW: hidden/minimized; no restore or capture fallback")
    return target


def geometry(hwnd):
    rect = W.RECT()
    check(U.GetClientRect(hwnd, C.byref(rect)), "GetClientRect")
    width, height = rect.right, rect.bottom
    if not (0 < width <= 8192 and 0 < height <= 8192 and width * height <= 20_000_000):
        raise PilotError("INVALID_SIZE: unsupported client dimensions")
    return width, height


def windows():
    result = []

    @CALLBACK
    def visit(hwnd, _):
        if U.IsWindowVisible(hwnd):
            try:
                row = asdict(identity(hwnd))
                row.update(title=text(hwnd), minimized=bool(U.IsIconic(hwnd)))
                result.append(row)
            except PilotError:
                pass
        return True

    check(U.EnumWindows(visit, 0), "EnumWindows")
    return result


def bindable(target):
    """An accessible top-level application window, never a desktop capture surface."""
    verify(target)
    if (U.GetAncestor(target.hwnd, 2) != target.hwnd
            or target.hwnd in (U.GetDesktopWindow(), U.GetShellWindow())
            or target.klass in ("Progman", "WorkerW")):
        raise PilotError("NOT_APPLICATION_TOP_LEVEL_WINDOW")
    dwm = C.WinDLL("dwmapi", use_last_error=True)
    attribute = api(dwm, "DwmGetWindowAttribute", C.c_long, W.HWND, W.DWORD, PTR, W.DWORD)
    cloaked = W.DWORD()
    if attribute(target.hwnd, 14, C.byref(cloaked), C.sizeof(cloaked)) != 0:
        raise PilotError("WINDOW_VISIBILITY_UNVERIFIABLE")
    if cloaked.value:
        raise PilotError("CLOAKED_WINDOW_UNAVAILABLE")
    geometry(target.hwnd)
    return verify(target)


def desktop_state():
    point = W.POINT()
    check(U.GetCursorPos(C.byref(point)), "GetCursorPos")
    return {"foreground": int(U.GetForegroundWindow() or 0), "cursor": [point.x, point.y]}


def click_desktop_diagnostic(before, after, target_hwnd):
    """Describe observed changes without attributing them to the posted click.

    A user can move their mouse or switch foreground apps during a target-local
    operation. These snapshots cannot identify the cause of either change.
    """
    return {"before": before, "after": after, "changed": before != after,
            "cursor_changed": before["cursor"] != after["cursor"],
            "foreground_changed": before["foreground"] != after["foreground"],
            "target_was_foreground": before["foreground"] == target_hwnd,
            "target_is_foreground_after": after["foreground"] == target_hwnd,
            "target_became_foreground": before["foreground"] != target_hwnd and after["foreground"] == target_hwnd,
            "attribution": "unknown; desktop snapshots do not identify the cause of a change"}


def png(width, height, bgra):
    rgb = bytearray(width * height * 3)
    rgb[0::3], rgb[1::3], rgb[2::3] = bgra[2::4], bgra[1::4], bgra[0::4]
    # Bounded sampling avoids allocating millions of Python color tuples.
    step = max(1, width * height // 65536)
    if len({tuple(rgb[i * 3:i * 3 + 3]) for i in range(0, width * height, step)}) < 4:
        raise PilotError("BLANK_FRAME: uniform/near-uniform client image rejected")
    stride = width * 3
    raw = b"".join(b"\0" + rgb[y * stride:(y + 1) * stride] for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def capture_worker(target):
    """Only this child performs the synchronous call; a parent timeout kills it."""
    verify(target)
    width, height = geometry(target.hwnd)
    # Create a memory-only DC/DIB. Never acquire or copy a desktop/window display DC.
    dc = check(G.CreateCompatibleDC(0), "CreateCompatibleDC")
    bitmap = previous = None
    try:
        header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, width * height * 4, 0, 0, 0, 0)
        bits = PTR()
        bitmap = check(G.CreateDIBSection(dc, C.c_char_p(header), 0, C.byref(bits), None, 0), "CreateDIBSection")
        previous = check(G.SelectObject(dc, bitmap), "SelectObject")
        C.memset(bits, 0, width * height * 4)
        C.set_last_error(0)
        rendered = U.PrintWindow(target.hwnd, dc, 3)
        last_error = C.get_last_error()  # read immediately, before any cleanup/verification API
        if not rendered:
            raise PilotError("CAPTURE_FAILED: PrintWindow returned 0; "
                             f"last_error={last_error} (diagnostic, not a guaranteed PrintWindow contract); no fallback")
        verify(target)
        if geometry(target.hwnd) != (width, height):
            raise PilotError("RESIZED_DURING_CAPTURE")
        return png(width, height, C.string_at(bits, width * height * 4))
    finally:
        if previous:
            G.SelectObject(dc, previous)
        if bitmap:
            G.DeleteObject(bitmap)
        G.DeleteDC(dc)


def runtime_command(command, *args):
    entry = Path(__file__).resolve().parents[2] / "scripts" / "runtime_entry.py"
    if not entry.is_file():
        raise PilotError("RUNTIME_ENTRY_MISSING")
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    return [str(python), "-I", "-S", str(entry), command, *args]


def capture(target, timeout=5, backend="printwindow"):
    if backend not in ("printwindow", "wgc"):
        raise PilotError("UNKNOWN_CAPTURE_BACKEND: select printwindow or wgc; no fallback")
    verify(target)
    before = desktop_state()
    try:
        child = subprocess.run(runtime_command("_capture", json.dumps(asdict(target)), "--backend", backend),
                               capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        raise PilotError("CAPTURE_TIMEOUT: worker terminated; no fallback") from exc
    after = desktop_state()
    verify(target)
    if child.returncode:
        raise PilotError(child.stderr.decode("utf-8", "replace")[-1500:])
    if not child.stdout.startswith(b"\x89PNG"):
        raise PilotError("CAPTURE_FAILED: worker returned no PNG")
    width, height = struct.unpack(">II", child.stdout[16:24])
    if geometry(target.hwnd) != (width, height):
        raise PilotError("RESIZED_DURING_CAPTURE")
    return child.stdout, (width, height), hashlib.sha256(child.stdout).hexdigest(), {
        "before": before, "after": after, "changed": before != after,
        "capture_method": "Windows.Graphics.Capture" if backend == "wgc" else "PrintWindow",
        "note": "Observation does not inject input; concurrent human activity is reported, not attributed to capture."}


def window_style(hwnd, index):
    C.set_last_error(0)
    value = window_long(hwnd, index)
    if not value and C.get_last_error():
        check(False, "GetWindowLong/style")
    return value & 0xffffffff


def embedded_process_chain(target, receiver):
    """Require a live same-user/session WebView2 descendant, not just SetParent."""
    if Path(receiver.exe).name.lower() != "msedgewebview2.exe":
        raise PilotError("UNSUPPORTED_EMBEDDED_PROCESS")
    class Entry(C.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("pid", W.DWORD),
                    ("heap", C.c_size_t), ("module", W.DWORD), ("threads", W.DWORD),
                    ("parent", W.DWORD), ("priority", W.LONG), ("flags", W.DWORD), ("name", W.WCHAR * 260)]
    snapshot_fn = api(K, "CreateToolhelp32Snapshot", W.HANDLE, W.DWORD, W.DWORD)
    first = api(K, "Process32FirstW", W.BOOL, W.HANDLE, C.POINTER(Entry))
    next_entry = api(K, "Process32NextW", W.BOOL, W.HANDLE, C.POINTER(Entry))
    snapshot = snapshot_fn(2, 0)
    if snapshot in (None, C.c_void_p(-1).value):
        raise PilotError("EMBEDDED_PROCESS_SNAPSHOT_FAILED")
    parents = {}
    try:
        item = Entry()
        item.dwSize = C.sizeof(item)
        check(first(snapshot, C.byref(item)), "Process32First/embedded")
        while True:
            parents[item.pid] = item.parent
            if not next_entry(snapshot, C.byref(item)):
                if C.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    check(False, "Process32Next/embedded")
                break
    finally:
        K.CloseHandle(snapshot)
    own, owner = process_scope(os.getpid()), process_scope(target.pid)
    sender_rid = input_integrity(os.getpid())
    if owner != own or not own["session"]:
        raise PilotError("EMBEDDED_USER_OR_SESSION_MISMATCH")
    chain, seen, pid, child_created = [], set(), receiver.pid, None
    for _ in range(32):
        if pid in seen or not pid:
            break
        seen.add(pid)
        created, exe = process_identity(pid)
        scope, rid = process_scope(pid), input_integrity(pid)
        if scope != owner or rid > sender_rid or (child_created is not None and created > child_created):
            raise PilotError("EMBEDDED_PROCESS_SCOPE_OR_ANCESTRY_MISMATCH")
        if process_identity(pid) != (created, exe):
            raise PilotError("EMBEDDED_PROCESS_REPLACED")
        chain.append({"pid": pid, "created": created, "exe": exe, "parent_pid": parents.get(pid),
                      "integrity_rid": rid, "session": scope["session"], "user_sid_digest": scope["user_sid_digest"]})
        if pid == target.pid:
            if (created, exe) != (target.created, target.exe):
                raise PilotError("EMBEDDED_OWNER_REPLACED")
            if (chain[0]["created"], chain[0]["exe"]) != (receiver.created, receiver.exe):
                raise PilotError("EMBEDDED_RECEIVER_REPLACED")
            return chain
        child_created, pid = created, parents.get(pid)
    raise PilotError("EMBEDDED_PROCESS_NOT_DESCENDANT: no live verified lineage to bound process")


def resolve_child(target, x, y, evidence):
    """Exact descendant hit-test; transparent traversal only for verified WebView2 hosting."""
    root = target.hwnd
    point = W.POINT(x, y)
    check(U.ClientToScreen(root, C.byref(point)), "ClientToScreen")
    current = root
    route, transparent_steps = evidence["route"], []
    evidence["transparent_steps"] = transparent_steps
    for _ in range(20):
        node = identity(current)
        local = W.POINT(point.x, point.y)
        check(U.ScreenToClient(current, C.byref(local)), "ScreenToClient")
        width, height = geometry(current)
        if not (0 <= local.x < width and 0 <= local.y < height):
            raise PilotError("CHILD_POINT_OUTSIDE_CLIENT")
        origin = W.POINT()
        check(U.ClientToScreen(current, C.byref(origin)), "ClientToScreen/child origin")
        if not U.IsWindowVisible(current) or not U.IsWindowEnabled(current):
            raise PilotError("CHILD_HIDDEN_OR_DISABLED")
        normal = int(U.ChildWindowFromPointEx(current, local, 7) or 0)
        inclusive = int(U.ChildWindowFromPointEx(current, local, 3) or 0)
        raw = int(U.ChildWindowFromPointEx(current, local, 0) or 0)
        route.append({**asdict(node), "parent_hwnd": int(U.GetAncestor(current, 1) or 0),
                      "client_size": [width, height], "client_origin_screen": [origin.x, origin.y],
                      "client_point": [local.x, local.y], "style": window_style(current, -16),
                      "ex_style": window_style(current, -20), "normal_child": normal,
                      "inclusive_child": inclusive, "first_child": raw})
        child = normal
        if inclusive != normal:
            host = identity(inclusive)
            step = len(route) - 1
            static_host = step == 0 and host.klass == "Static" and host.pid == target.pid
            render_leaf = (step == 3 and node.klass == "Chrome_WidgetWin_1"
                           and host.klass == "Chrome_RenderWidgetHostHWND"
                           and host.pid == node.pid != target.pid
                           and (host.created, host.exe) == (node.created, node.exe)
                           and [row["klass"] for row in route[1:]] ==
                               ["Static", "Chrome_WidgetWin_0", "Chrome_WidgetWin_1"]
                           and all(row["pid"] == target.pid for row in route[:3])
                           and normal == current and raw == inclusive)
            if (not (static_host or render_leaf) or not window_style(inclusive, -20) & 0x20):
                raise PilotError("UNSUPPORTED_TRANSPARENT_CHILD: no blind overlay traversal")
            transparent_steps.append(step)
            child = inclusive
        if not child:
            raise PilotError("CHILD_HIT_TEST_FAILED")
        if child == current:
            break
        if (U.GetAncestor(child, 2) != root or U.GetAncestor(child, 1) != current
                or not window_style(child, -16) & 0x40000000):  # WS_CHILD; true parent, not owner
            raise PilotError("CHILD_ESCAPE: rejected window outside target")
        current = child
    else:
        raise PilotError("CHILD_DEPTH_EXCEEDED")
    embedded = any(row["pid"] != target.pid for row in route)
    if embedded or transparent_steps:
        if (len(route) != 5 or [row["klass"] for row in route[1:]] !=
                ["Static", "Chrome_WidgetWin_0", "Chrome_WidgetWin_1", "Chrome_RenderWidgetHostHWND"]
                or transparent_steps not in ([0], [0, 3])
                or bool(route[4]["ex_style"] & 0x20) != (transparent_steps == [0, 3])
                or any(row["pid"] != target.pid for row in route[:3])
                or route[3]["pid"] == target.pid or route[3]["pid"] != route[4]["pid"]
                or any(row["first_child"] != row["inclusive_child"] for row in route)):
            raise PilotError("UNVERIFIED_EMBEDDED_HOST_CHAIN: unsupported or obstructed")
        evidence["process_chain"] = embedded_process_chain(target, node)
        evidence["policy"] = "verified_static_webview2_descendant"
    else:
        evidence["policy"] = "same_process_child"
    access = input_access(node)
    if access["blocked_by_integrity"]:
        raise PilotError("HIGHER_INTEGRITY_RECEIVER")
    evidence.update(receiver=asdict(node), receiver_point=[local.x, local.y], integrity=access)
    return current, local.x, local.y


def post(hwnd, msg, wp=0, lp=0):
    check(U.PostMessageW(hwnd, msg, wp, lp), "PostMessage (UIPI may block a higher-integrity target)")


def click(target, size, x, y, before_dispatch=None):
    evidence = {"bound_window": asdict(target), "root_point": [x, y], "route": [],
                "down_posted": False, "up_posted": False, "effect": "unverified"}
    try:
        return _click(target, size, x, y, evidence, before_dispatch)
    except Exception as exc:
        exc.click_evidence = evidence
        raise


def _click(target, size, x, y, evidence, before_dispatch):
    verify(target)
    if geometry(target.hwnd) != tuple(size):
        raise PilotError("STALE_FRAME: resized; observe again")
    if type(x) is not int or type(y) is not int or not (0 <= x < size[0] and 0 <= y < size[1]):
        raise PilotError("INVALID_POINT: use unscaled client-image pixel coordinates")
    before = desktop_state()
    evidence["desktop_before"] = before
    hwnd, cx, cy = resolve_child(target, x, y, evidence)
    child_identity = identity(hwnd)

    def revalidate(stage):
        verify(target)
        if geometry(target.hwnd) != tuple(size):
            raise PilotError("STALE_FRAME: resized; " + stage)
        current = {"route": []}
        resolve_child(target, x, y, current)
        for key in ("route", "receiver", "receiver_point", "policy", "process_chain", "integrity", "transparent_steps"):
            if current.get(key) != evidence.get(key):
                raise PilotError("STALE_CHILD_ROUTE: " + stage)
        if identity(hwnd) != child_identity:
            raise PilotError("STALE_CHILD_WINDOW: " + stage)

    if before_dispatch:
        before_dispatch(evidence)  # durable exact receiver evidence before any message
    revalidate("before down")
    point = (cy & 0xffff) << 16 | (cx & 0xffff)

    try:
        # Deliberately no mouse-move, global hit-test, focus or activation call.
        post(hwnd, 0x0201, 1, point)  # WM_LBUTTONDOWN
        evidence["down_posted"] = True
    except PilotError as exc:
        raise PilotError(f"DISPATCH_FAILED: input_sent=false; {exc}") from exc
    release_posted = False
    try:
        revalidate("before release")
        post(hwnd, 0x0202, 0, point)  # WM_LBUTTONUP
        release_posted = True
        evidence["up_posted"] = True
        result = C.c_size_t()
        check(U.SendMessageTimeoutW(hwnd, 0, 0, 0, 2, 1000, C.byref(result)), "message barrier")
        time.sleep(0.1)
        revalidate("after dispatch")
        after = desktop_state()
    except Exception as exc:
        raise PilotError("POST_DISPATCH_ERROR: input_sent=true; down_posted=true; "
                         f"up_posted={str(release_posted).lower()}; effect=unverified; do not replay; {exc}") from exc
    observation = click_desktop_diagnostic(before, after, target.hwnd)
    evidence["desktop_observation"] = observation
    return {"dispatch": "posted", "input_sent": True, "effect": "unverified", "method": "PostMessageW",
            "click_evidence": evidence, "desktop": before,
            "desktop_observation": observation}


def close_window(target):
    verify(target)
    before = desktop_state()
    post(target.hwnd, 0x0010)  # WM_CLOSE only: no force kill, no global close shortcut
    deadline = time.monotonic() + 8
    while U.IsWindow(target.hwnd) and time.monotonic() < deadline:
        time.sleep(0.1)
    if U.IsWindow(target.hwnd):
        raise PilotError("CLOSE_NOT_CONFIRMED: prompt/hang; no forced termination")
    return {"before": before, "after": desktop_state(), "message": "WM_CLOSE", "window_closed": True}


def processes_for(exe):
    """Toolhelp process enumeration; exact image paths, never process-name termination."""
    class Entry(C.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ProcessID", W.DWORD),
                    ("th32DefaultHeapID", C.c_size_t), ("th32ModuleID", W.DWORD),
                    ("cntThreads", W.DWORD), ("th32ParentProcessID", W.DWORD),
                    ("pcPriClassBase", W.LONG), ("dwFlags", W.DWORD), ("szExeFile", W.WCHAR * 260)]

    api(K, "CreateToolhelp32Snapshot", W.HANDLE, W.DWORD, W.DWORD)
    api(K, "Process32FirstW", W.BOOL, W.HANDLE, C.POINTER(Entry))
    api(K, "Process32NextW", W.BOOL, W.HANDLE, C.POINTER(Entry))
    snapshot = K.CreateToolhelp32Snapshot(2, 0)
    if snapshot in (None, C.c_void_p(-1).value):
        raise PilotError("PROCESS_ENUM_FAILED")
    found = []
    try:
        item = Entry()
        item.dwSize = C.sizeof(item)
        more = K.Process32FirstW(snapshot, C.byref(item))
        while more:
            try:
                created, path = process_identity(item.th32ProcessID)
                if path == canonical(exe):
                    found.append({"pid": item.th32ProcessID, "created": created, "exe": path})
            except PilotError:
                pass
            more = K.Process32NextW(snapshot, C.byref(item))
        return found
    finally:
        K.CloseHandle(snapshot)
