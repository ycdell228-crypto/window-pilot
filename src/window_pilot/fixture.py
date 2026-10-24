"""A disposable native test window, covered by a separate opaque window.

Both are shown without activation. Only this fixture accepts test-only messages.
"""
import ctypes as C
from ctypes import wintypes as W
import time

from .win32 import U, G, K, PTR, api, check


def run():
    PROC = C.WINFUNCTYPE(C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)

    class WndClass(C.Structure):
        _fields_ = [("style", W.UINT), ("proc", PROC), ("clsExtra", C.c_int), ("wndExtra", C.c_int),
                    ("instance", W.HINSTANCE), ("icon", W.HICON), ("cursor", W.HANDLE),
                    ("background", W.HBRUSH), ("menu", W.LPCWSTR), ("name", W.LPCWSTR)]

    class Paint(C.Structure):
        _fields_ = [("hdc", W.HDC), ("erase", W.BOOL), ("rect", W.RECT),
                    ("restore", W.BOOL), ("inc", W.BOOL), ("reserved", C.c_byte * 32)]

    api(K, "GetModuleHandleW", W.HMODULE, W.LPCWSTR)
    api(U, "RegisterClassW", W.ATOM, C.POINTER(WndClass))
    api(U, "CreateWindowExW", W.HWND, W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
        C.c_int, C.c_int, C.c_int, C.c_int, W.HWND, W.HMENU, W.HINSTANCE, PTR)
    api(U, "DefWindowProcW", C.c_ssize_t, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
    api(U, "BeginPaint", W.HDC, W.HWND, C.POINTER(Paint))
    api(U, "EndPaint", W.BOOL, W.HWND, C.POINTER(Paint))
    api(U, "FillRect", C.c_int, W.HDC, C.POINTER(W.RECT), W.HBRUSH)
    api(U, "DrawTextW", C.c_int, W.HDC, W.LPCWSTR, C.c_int, C.POINTER(W.RECT), W.UINT)
    api(U, "SetWindowTextW", W.BOOL, W.HWND, W.LPCWSTR)
    api(U, "ShowWindow", W.BOOL, W.HWND, C.c_int)
    api(U, "DestroyWindow", W.BOOL, W.HWND)
    api(U, "InvalidateRect", W.BOOL, W.HWND, PTR, W.BOOL)
    api(U, "GetMessageW", W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
    api(U, "TranslateMessage", W.BOOL, C.POINTER(W.MSG))
    api(U, "DispatchMessageW", C.c_ssize_t, C.POINTER(W.MSG))
    api(U, "PostQuitMessage", None, C.c_int)
    api(U, "SetTimer", C.c_size_t, W.HWND, C.c_size_t, W.UINT, PTR)
    api(G, "CreateSolidBrush", W.HBRUSH, W.DWORD)
    api(G, "SetTextColor", W.DWORD, W.HDC, W.DWORD)
    api(G, "SetBkMode", C.c_int, W.HDC, C.c_int)
    clicks, blank, cover = 0, False, None
    started = time.monotonic()

    def paint(hwnd, dc, is_cover=False):
        rect = W.RECT()
        U.GetClientRect(hwnd, C.byref(rect))
        colors = [0x994411] if is_cover else ([0] if blank else [0x2233dd, 0x33bb22, 0xdd6633, 0x22dddd])
        for index, color in enumerate(colors):
            area = W.RECT(index * rect.right // len(colors), 0, (index + 1) * rect.right // len(colors), rect.bottom)
            brush = G.CreateSolidBrush(color)
            U.FillRect(dc, C.byref(area), brush)
            G.DeleteObject(brush)
        if not blank or is_cover:
            G.SetTextColor(dc, 0xffffff)
            G.SetBkMode(dc, 1)
            label = "OPAQUE COVER - MUST NOT APPEAR IN CAPTURE" if is_cover else f"WINDOW PILOT TARGET | clicks={clicks}\nClick anywhere. No keyboard needed."
            U.DrawTextW(dc, label, -1, C.byref(rect), 0x25)

    @PROC
    def procedure(hwnd, msg, wp, lp):
        nonlocal clicks, blank, cover
        try:
            is_cover = hwnd == cover
            if msg == 0x000f:
                state = Paint()
                dc = U.BeginPaint(hwnd, C.byref(state))
                paint(hwnd, dc, is_cover)
                U.EndPaint(hwnd, C.byref(state))
                return 0
            if msg == 0x0318:  # WM_PRINTCLIENT
                paint(hwnd, wp, is_cover)
                return 1
            if msg == 0x0202 and not is_cover:
                clicks += 1
                U.SetWindowTextW(hwnd, f"Window Pilot Test | clicks={clicks}")
                U.InvalidateRect(hwnd, None, True)
                return 0
            if msg == 0x0021:
                return 3  # MA_NOACTIVATE
            if msg == 0x8001 and not is_cover:
                blank = bool(wp)
                U.InvalidateRect(hwnd, None, True)
                return 0
            if msg == 0x8002 and not is_cover:
                time.sleep(8)  # test the parent's hard capture timeout
                return 0
            if msg == 0x0113 and time.monotonic() - started > 600:
                U.DestroyWindow(hwnd)
                return 0
            if msg == 0x0002 and not is_cover:
                if cover:
                    U.DestroyWindow(cover)
                U.PostQuitMessage(0)
                return 0
        except Exception:
            return 0
        return U.DefWindowProcW(hwnd, msg, wp, lp)

    instance = K.GetModuleHandleW(None)
    for name in ("WindowPilotFixture", "WindowPilotCover"):
        cls = WndClass(0, procedure, 0, 0, instance, None, None, None, None, name)
        check(U.RegisterClassW(C.byref(cls)), "RegisterClass")
    # WS_EX_NOACTIVATE; neither window can acquire focus by clicking its chrome.
    target = check(U.CreateWindowExW(0x08000000, "WindowPilotFixture", "Window Pilot Test | clicks=0",
                                    0x00cf0000, 100, 100, 520, 360, None, None, instance, None), "fixture")
    U.ShowWindow(target, 4)
    # WS_EX_NOACTIVATE | WS_EX_TOPMOST; the target is completely occluded.
    cover = check(U.CreateWindowExW(0x08000008, "WindowPilotCover", "Window Pilot Opaque Cover",
                                   0x00cf0000, 100, 100, 540, 380, None, None, instance, None), "cover")
    U.ShowWindow(cover, 4)
    U.SetTimer(target, 1, 1000, None)
    message = W.MSG()
    while U.GetMessageW(C.byref(message), None, 0, 0) > 0:
        U.TranslateMessage(C.byref(message))
        U.DispatchMessageW(C.byref(message))
