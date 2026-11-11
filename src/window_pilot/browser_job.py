"""Windows kill-on-close job for the owned Node/Chrome tree; never attach user processes."""
import ctypes as C
from ctypes import wintypes as W
import time


class Limits(C.Structure):
    _fields_ = [('process_time', C.c_longlong), ('job_time', C.c_longlong), ('flags', W.DWORD),
                ('min_working', C.c_size_t), ('max_working', C.c_size_t), ('active_limit', W.DWORD),
                ('affinity', C.c_size_t), ('priority', W.DWORD), ('scheduling', W.DWORD)]


class IO(C.Structure):
    _fields_ = [(name, C.c_ulonglong) for name in ('read_ops', 'write_ops', 'other_ops', 'read_bytes', 'write_bytes', 'other_bytes')]


class Extended(C.Structure):
    _fields_ = [('basic', Limits), ('io', IO), ('process_memory', C.c_size_t), ('job_memory', C.c_size_t),
                ('peak_process_memory', C.c_size_t), ('peak_job_memory', C.c_size_t)]


class Accounting(C.Structure):
    _fields_ = [(name, C.c_longlong) for name in ('user', 'kernel', 'period_user', 'period_kernel')] + [
        (name, W.DWORD) for name in ('page_faults', 'total', 'active', 'terminated')]


class BrowserJob:
    def __init__(self):
        self.api = C.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [C.c_void_p, W.LPCWSTR], W.HANDLE),
            ('SetInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            ('AssignProcessToJobObject', [W.HANDLE, W.HANDLE], W.BOOL),
            ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            ('QueryInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            ('TerminateJobObject', [W.HANDLE, W.UINT], W.BOOL),
            ('CloseHandle', [W.HANDLE], W.BOOL),
        ):
            fn = getattr(self.api, name); fn.argtypes = args; fn.restype = result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise OSError('BROWSER_JOB_CREATE_FAILED')
        limits = Extended(); limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, C.byref(limits), C.sizeof(limits)):
            self.close()
            raise OSError('BROWSER_JOB_CONFIGURE_FAILED')

    def assign(self, pid):
        process = self.api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        try:
            if not process or not self.api.AssignProcessToJobObject(self.handle, process):
                raise OSError('BROWSER_JOB_ASSIGN_FAILED')
        finally:
            if process:
                self.api.CloseHandle(process)

    def finish(self):
        # Worker has exited; terminate any orphaned descendants in this dedicated job only.
        self.api.TerminateJobObject(self.handle, 1)
        deadline = time.monotonic() + 3
        try:
            while time.monotonic() < deadline:
                info = Accounting()
                if not self.api.QueryInformationJobObject(self.handle, 1, C.byref(info), C.sizeof(info), None):
                    return False
                if info.active == 0:
                    return True
                time.sleep(0.02)
            return False
        finally:
            self.close()

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
