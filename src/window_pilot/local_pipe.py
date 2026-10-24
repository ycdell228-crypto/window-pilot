"""Local-only Windows named pipe with explicit ACL, peer PID checks and bounded frames."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import json
import struct
import time

from . import win32 as w

K = w.K
A = C.WinDLL("advapi32", use_last_error=True)
PTR = C.c_void_p
INVALID = C.c_void_p(-1).value
MAX_FRAME = 2 * 1024 * 1024


class Security(C.Structure):
    _fields_ = [("length", W.DWORD), ("descriptor", PTR), ("inherit", W.BOOL)]


class Overlapped(C.Structure):
    _fields_ = [("internal", C.c_size_t), ("internal_high", C.c_size_t),
                ("offset", W.DWORD), ("offset_high", W.DWORD), ("event", W.HANDLE)]


w.api(A, "ConvertStringSecurityDescriptorToSecurityDescriptorW", W.BOOL, W.LPCWSTR, W.DWORD, C.POINTER(PTR), PTR)
w.api(K, "LocalFree", PTR, PTR)
w.api(K, "CreateNamedPipeW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, W.DWORD, C.POINTER(Security))
w.api(K, "ConnectNamedPipe", W.BOOL, W.HANDLE, C.POINTER(Overlapped))
w.api(K, "DisconnectNamedPipe", W.BOOL, W.HANDLE)
w.api(K, "CreateFileW", W.HANDLE, W.LPCWSTR, W.DWORD, W.DWORD, PTR, W.DWORD, W.DWORD, W.HANDLE)
w.api(K, "WaitNamedPipeW", W.BOOL, W.LPCWSTR, W.DWORD)
w.api(K, "CreateEventW", W.HANDLE, PTR, W.BOOL, W.BOOL, W.LPCWSTR)
w.api(K, "ReadFile", W.BOOL, W.HANDLE, PTR, W.DWORD, C.POINTER(W.DWORD), C.POINTER(Overlapped))
w.api(K, "WriteFile", W.BOOL, W.HANDLE, PTR, W.DWORD, C.POINTER(W.DWORD), C.POINTER(Overlapped))
w.api(K, "GetOverlappedResult", W.BOOL, W.HANDLE, C.POINTER(Overlapped), C.POINTER(W.DWORD), W.BOOL)
w.api(K, "CancelIoEx", W.BOOL, W.HANDLE, C.POINTER(Overlapped))
w.api(K, "WaitForSingleObject", W.DWORD, W.HANDLE, W.DWORD)
w.api(K, "GetNamedPipeClientProcessId", W.BOOL, W.HANDLE, C.POINTER(W.ULONG))
w.api(K, "GetNamedPipeServerProcessId", W.BOOL, W.HANDLE, C.POINTER(W.ULONG))


class Connection:
    def __init__(self, handle, stop=None):
        self.handle, self.stop = handle, stop

    def close(self):
        if self.handle is not None:
            K.CloseHandle(self.handle)
            self.handle = None

    def complete(self, operation, transferred, timeout):
        deadline = time.monotonic() + timeout if timeout is not None else None
        while K.WaitForSingleObject(operation.event, 100) == 0x102:
            if (self.stop and self.stop.is_set()) or (deadline is not None and time.monotonic() >= deadline):
                K.CancelIoEx(self.handle, C.byref(operation))
                # Keep OVERLAPPED/buffer alive until cancellation actually completes.
                K.GetOverlappedResult(self.handle, C.byref(operation), C.byref(transferred), True)
                raise w.PilotError("PIPE_STOPPED_OR_TIMEOUT: outcome may be unknown; never replay")
        if not K.GetOverlappedResult(self.handle, C.byref(operation), C.byref(transferred), False):
            error = C.get_last_error()
            if error in (109, 232, 995):
                raise EOFError("pipe disconnected; no automatic retry")
            raise w.PilotError(f"PIPE_IO_ERROR: {error}; no retry")

    def io(self, buffer, count, reading, timeout):
        event = w.check(K.CreateEventW(None, True, False, None), "pipe event")
        operation, transferred = Overlapped(event=event), W.DWORD()
        try:
            fn = K.ReadFile if reading else K.WriteFile
            if not fn(self.handle, buffer, count, C.byref(transferred), C.byref(operation)):
                if C.get_last_error() != 997:
                    raise EOFError(f"pipe closed/error {C.get_last_error()}; action outcome unknown; no replay")
                self.complete(operation, transferred, timeout)
            if transferred.value == 0:
                raise EOFError("pipe closed")
            return transferred.value
        finally:
            K.CloseHandle(event)

    def read_exact(self, count, timeout):
        result = bytearray()
        while len(result) < count:
            buffer = C.create_string_buffer(count - len(result))
            used = self.io(buffer, len(buffer), True, timeout)
            result.extend(buffer.raw[:used])
        return bytes(result)

    def receive(self, timeout=None):
        length = struct.unpack("<I", self.read_exact(4, timeout))[0]
        if not 0 < length <= MAX_FRAME:
            raise w.PilotError("PIPE_FRAME_SIZE_REJECTED")
        return json.loads(self.read_exact(length, 5 if timeout is None else timeout).decode("utf8"))

    def send(self, value):
        data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf8")
        if len(data) > MAX_FRAME:
            raise w.PilotError("PIPE_RESPONSE_TOO_LARGE")
        remaining = struct.pack("<I", len(data)) + data
        while remaining:
            buffer = C.create_string_buffer(remaining)
            used = self.io(buffer, len(remaining), False, 5)
            remaining = remaining[used:]

    def peer(self, server_side):
        pid = W.ULONG()
        fn = K.GetNamedPipeClientProcessId if server_side else K.GetNamedPipeServerProcessId
        w.check(fn(self.handle, C.byref(pid)), "named-pipe peer PID")
        created, exe = w.process_identity(pid.value)
        return {"pid": pid.value, "created": created, "exe": exe, **w.process_scope(pid.value),
                "integrity_rid": w.input_integrity(pid.value)}


def listen(name, sid, stop, first=False):
    if not name.startswith("\\\\.\\pipe\\WindowPilot."):
        raise w.PilotError("INVALID_LOCAL_PIPE_NAME")
    descriptor = PTR()
    # Low user gets read/write/synchronize, NOT FILE_CREATE_PIPE_INSTANCE (0x4).
    # Elevated Administrators can create additional instances; peers are still SID/session checked.
    sddl = "D:P(A;;GA;;;BA)(A;;0x12019b;;;" + sid + ")"
    w.check(A.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl, 1, C.byref(descriptor), None), "pipe ACL")
    try:
        attributes = Security(C.sizeof(Security), descriptor, False)
        handle = K.CreateNamedPipeW(name, 3 | 0x40000000 | (0x00080000 if first else 0),
                                    0x8, 5, 65536, 65536, 3000, C.byref(attributes))
        if handle == INVALID:
            raise w.PilotError(f"PIPE_CREATE_FAILED: {C.get_last_error()}")
    finally:
        K.LocalFree(descriptor)
    connection = Connection(handle, stop)
    event = w.check(K.CreateEventW(None, True, False, None), "pipe connect event")
    operation, transferred = Overlapped(event=event), W.DWORD()
    try:
        if not K.ConnectNamedPipe(handle, C.byref(operation)):
            error = C.get_last_error()
            if error == 997:
                connection.complete(operation, transferred, None)
            elif error != 535:
                raise w.PilotError(f"PIPE_CONNECT_FAILED: {error}")
        return connection
    except BaseException:
        connection.close()
        raise
    finally:
        K.CloseHandle(event)


def connect(name):
    if not name.startswith("\\\\.\\pipe\\WindowPilot."):
        raise w.PilotError("INVALID_LOCAL_PIPE_NAME")
    # One connection attempt. A failed call is never replayed or sent to a direct fallback.
    w.check(K.WaitNamedPipeW(name, 3000), "ADMIN_SERVICE_UNAVAILABLE: start/check the dedicated task")
    handle = K.CreateFileW(name, 0x12019b, 0, None, 3, 0x40000000, None)
    if handle == INVALID:
        raise w.PilotError(f"PIPE_OPEN_FAILED: {C.get_last_error()}")
    return Connection(handle)
