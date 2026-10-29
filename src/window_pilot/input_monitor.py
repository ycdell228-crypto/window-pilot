"""Action-scoped, pass-through low-level hooks. No event payload is persisted."""
import ctypes as C
from ctypes import wintypes as W
import secrets
import threading
import time
from . import win32 as w


class MonitorError(w.PilotError):
    pass


class KeyEvent(C.Structure):
    _fields_ = [("vk", W.DWORD), ("scan", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", C.c_size_t)]


class MouseEvent(C.Structure):
    _fields_ = [("point", W.POINT), ("data", W.DWORD), ("flags", W.DWORD),
                ("time", W.DWORD), ("extra", C.c_size_t)]


HOOK = C.WINFUNCTYPE(C.c_ssize_t, C.c_int, W.WPARAM, W.LPARAM)
w.api(w.U, "SetWindowsHookExW", W.HANDLE, C.c_int, HOOK, W.HINSTANCE, W.DWORD)
w.api(w.U, "CallNextHookEx", C.c_ssize_t, W.HANDLE, C.c_int, W.WPARAM, W.LPARAM)
w.api(w.U, "UnhookWindowsHookEx", W.BOOL, W.HANDLE)
w.api(w.U, "PostThreadMessageW", W.BOOL, W.DWORD, W.UINT, W.WPARAM, W.LPARAM)
w.api(w.U, "PeekMessageW", W.BOOL, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT, W.UINT)
w.api(w.U, "GetMessageW", C.c_int, C.POINTER(W.MSG), W.HWND, W.UINT, W.UINT)
w.api(w.U, "SetTimer", C.c_size_t, W.HWND, C.c_size_t, W.UINT, C.c_void_p)
w.api(w.U, "KillTimer", W.BOOL, W.HWND, C.c_size_t)
w.api(w.K, "GetCurrentThreadId", W.DWORD)
w.api(w.K, "GetModuleHandleW", W.HMODULE, W.LPCWSTR)


def exact_key(vk, scan=0, extended=False):
    if vk == 16:
        return 161 if scan == 0x36 else 160
    if vk in (17, 18):
        return {17: 162, 18: 164}[vk] + bool(extended)
    return vk


class InputMonitor:
    def __init__(self):
        self.marker = secrets.randbits(31) or 1  # portable through Windows input paths retaining 32-bit extra info
        self.interrupted = threading.Event()
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.external_down = set()
        self.counts = {"own_keyboard":0, "own_mouse":0, "external_keyboard":0,
                       "external_mouse_move":0, "external_mouse_other":0, "stationary_mouse_notifications":0,
                       "external_injected":0, "external_noninjected":0}
        point=W.POINT()
        w.check(w.U.GetCursorPos(C.byref(point)),"input_monitor_cursor")
        self.pointer=(point.x,point.y)
        self.failed = False
        self.cleanup_failed = False
        self.closed = False
        self.thread_id = None
        self.last_ack = time.monotonic()
        self.last_ping = self.last_ack
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        try:
            if not self.ready.wait(2) or self.failed:
                raise MonitorError("FOREGROUND_INPUT_MONITOR_UNAVAILABLE")
            self.check()
        except BaseException:
            self.close()
            raise

    def _run(self):
        hooks = []
        timer = 0
        def record(code, message, address, keyboard):
            try:
                if code >= 0:
                    event = C.cast(address, C.POINTER(KeyEvent if keyboard else MouseEvent)).contents
                    own = event.extra == self.marker and bool(event.flags & (0x10 if keyboard else 1))
                    kind = ("own_keyboard" if keyboard else "own_mouse") if own else (
                        "external_keyboard" if keyboard else "external_mouse_move" if message == 0x200 else "external_mouse_other")
                    if not keyboard and message == 0x200:
                        position=(event.point.x,event.point.y)
                        if not own and position==self.pointer: self.counts["stationary_mouse_notifications"]+=1
                        self.pointer=position
                    self.counts[kind] += 1
                    if not own:
                        self.counts["external_injected" if event.flags & (0x10 if keyboard else 1) else "external_noninjected"]+=1
                        with self.lock:
                            if keyboard:
                                key = exact_key(event.vk, event.scan, bool(event.flags & 1))
                                if message in (0x100, 0x104): self.external_down.add(key)
                                elif message in (0x101, 0x105): self.external_down.discard(key)
                            else:
                                pair = {0x201:(1,True), 0x202:(1,False), 0x204:(2,True), 0x205:(2,False),
                                        0x207:(4,True), 0x208:(4,False),
                                        0x20b:(5 if event.data >> 16 == 1 else 6,True),
                                        0x20c:(5 if event.data >> 16 == 1 else 6,False)}.get(message)
                                if pair:
                                    if pair[1]: self.external_down.add(pair[0])
                                    else: self.external_down.discard(pair[0])
                        self.interrupted.set()  # latch even if a short tap ends before next safety check
            except BaseException:
                self.failed = True
                self.interrupted.set()
            return w.U.CallNextHookEx(None, code, message, address)  # never swallow user input
        self.keyboard_callback = HOOK(lambda c,m,p: record(c,m,p,True))
        self.mouse_callback = HOOK(lambda c,m,p: record(c,m,p,False))
        try:
            self.thread_id = w.K.GetCurrentThreadId()
            message = W.MSG()
            w.U.PeekMessageW(C.byref(message), None, 0, 0, 0)  # create thread queue before ready
            module = w.K.GetModuleHandleW(None)
            for kind, callback in ((13,self.keyboard_callback),(14,self.mouse_callback)):
                if self.stop.is_set(): return
                hook = w.U.SetWindowsHookExW(kind, callback, module, 0)
                if not hook: raise MonitorError("FOREGROUND_INPUT_MONITOR_UNAVAILABLE")
                hooks.append(hook)
            timer = w.U.SetTimer(None, 0, 100, None)
            if not timer: raise MonitorError("FOREGROUND_INPUT_MONITOR_UNAVAILABLE")
            self.ready.set()
            while not self.stop.is_set():
                result = w.U.GetMessageW(C.byref(message), None, 0, 0)
                if result == 0: break
                if result < 0: raise MonitorError("FOREGROUND_INPUT_MONITOR_UNAVAILABLE")
                self.last_ack = time.monotonic()
        except BaseException:
            self.failed = True
        finally:
            if timer and not w.U.KillTimer(None, timer): self.failed = self.cleanup_failed = True
            for hook in reversed(hooks):
                if not w.U.UnhookWindowsHookEx(hook): self.failed = self.cleanup_failed = True
            self.ready.set()

    def healthy(self):
        return not self.failed and self.thread.is_alive() and not self.closed

    def check(self):
        now = time.monotonic()
        if not self.healthy():
            raise MonitorError("FOREGROUND_INPUT_MONITOR_UNAVAILABLE")
        if now - self.last_ping > 0.1:
            if not w.U.PostThreadMessageW(self.thread_id, 0x8001, 0, 0):
                self.failed = True
                raise MonitorError("FOREGROUND_INPUT_MONITOR_UNAVAILABLE")
            self.last_ping = now
        if now - self.last_ack > 0.75:
            self.failed = True
            raise MonitorError("FOREGROUND_INPUT_MONITOR_UNAVAILABLE")
        if self.interrupted.is_set():
            raise MonitorError("FOREGROUND_EXTERNAL_INPUT")

    def tag(self, event):
        if event.type == 1: event.ki.extra = self.marker
        else: event.mi.extra = self.marker
        return event

    def may_release(self, key):
        with self.lock:
            return key not in self.external_down  # monitor failure alone is not evidence of external ownership

    def close(self):
        if self.closed: return
        self.stop.set()
        if self.thread.is_alive() and self.thread_id is not None:
            if not w.U.PostThreadMessageW(self.thread_id, 0x12, 0, 0): self.failed = self.cleanup_failed = True
        self.thread.join(timeout=2)
        self.closed = True
        if self.thread.is_alive() or self.cleanup_failed:
            raise MonitorError("FOREGROUND_INPUT_MONITOR_CLEANUP_FAILED")
