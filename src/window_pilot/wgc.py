"""Optional WGC window-only backend. No picker, monitor capture or input APIs."""
from __future__ import annotations

import asyncio
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path
import sys
import time
import uuid

from . import win32 as w


def load_dependencies():
    # Project-local binary wheels; never install/modify a global interpreter here.
    local = Path(__file__).resolve().parents[2] / ".local" / "wgc-deps"
    if local.is_dir() and str(local) not in sys.path:
        sys.path.insert(0, str(local))
    try:
        from winrt.runtime import init_apartment, ApartmentType
        from winrt.windows.graphics.capture import Direct3D11CaptureFramePool, GraphicsCaptureSession
        from winrt.windows.graphics.capture.interop import create_for_window
        from winrt.windows.graphics.directx import DirectXPixelFormat
        from winrt.windows.graphics.directx.direct3d11.interop import create_direct3d11_device_from_dxgi_device
        from winrt.windows.graphics.imaging import SoftwareBitmap
        from winrt.windows.storage.streams import Buffer
    except ImportError as exc:
        raise w.PilotError("WGC_DEPENDENCY_MISSING: install the project's optional WGC dependencies; no fallback") from exc
    return (init_apartment, ApartmentType, Direct3D11CaptureFramePool, GraphicsCaptureSession,
            create_for_window, DirectXPixelFormat, create_direct3d11_device_from_dxgi_device, SoftwareBitmap, Buffer)


def hresult(value, operation):
    if value < 0:
        raise w.PilotError(f"WGC_FAILED: {operation}: HRESULT 0x{value & 0xffffffff:08x}")


def com_method(pointer, slot, result, *args):
    table = C.cast(pointer, C.POINTER(C.POINTER(C.c_void_p))).contents
    return C.WINFUNCTYPE(result, C.c_void_p, *args)(table[slot])


def release(pointer):
    if pointer:
        com_method(pointer, 2, W.ULONG)(pointer)


def make_device(wrap_device):
    d3d = C.WinDLL("d3d11", use_last_error=True)
    create = w.api(d3d, "D3D11CreateDevice", C.c_long, C.c_void_p, W.UINT, W.HMODULE,
                   W.UINT, C.c_void_p, W.UINT, W.UINT, C.POINTER(C.c_void_p),
                   C.POINTER(W.UINT), C.POINTER(C.c_void_p))
    device, context, dxgi = C.c_void_p(), C.c_void_p(), C.c_void_p()
    level = W.UINT()
    try:
        hresult(create(None, 1, None, 0x20, None, 0, 7, C.byref(device), C.byref(level), C.byref(context)), "D3D11CreateDevice")
        iid = (C.c_ubyte * 16).from_buffer_copy(uuid.UUID("54ec77fa-1377-44e6-8c32-88fd5f44c84c").bytes_le)
        query = com_method(device, 0, C.c_long, C.c_void_p, C.POINTER(C.c_void_p))
        hresult(query(device, C.byref(iid), C.byref(dxgi)), "QueryInterface(IDXGIDevice)")
        return wrap_device(dxgi.value)
    finally:
        release(dxgi)
        release(context)
        release(device)


def client_geometry(target):
    """Relative client rectangle within the target's DWM composition bounds."""
    w.verify(target)
    width, height = w.geometry(target.hwnd)
    dwm = C.WinDLL("dwmapi", use_last_error=True)
    get_bounds = w.api(dwm, "DwmGetWindowAttribute", C.c_long, W.HWND, W.DWORD, C.c_void_p, W.DWORD)
    rect, origin = W.RECT(), W.POINT(0, 0)
    hresult(get_bounds(target.hwnd, 9, C.byref(rect), C.sizeof(rect)), "DWM extended frame bounds")
    w.check(w.U.ClientToScreen(target.hwnd, C.byref(origin)), "ClientToScreen")
    full_width, full_height = rect.right - rect.left, rect.bottom - rect.top
    if not (0 < full_width <= 8192 and 0 < full_height <= 8192 and full_width * full_height <= 20_000_000):
        raise w.PilotError("WGC_INVALID_SIZE: unsupported composition dimensions")
    x, y = origin.x - rect.left, origin.y - rect.top
    if not (0 <= x and 0 <= y and x + width <= full_width and y + height <= full_height):
        raise w.PilotError("WGC_GEOMETRY_MISMATCH: client area not inside target composition bounds")
    return full_width, full_height, x, y, width, height


def crop_client(data, full_width, full_height, x, y, width, height):
    if len(data) != full_width * full_height * 4:
        raise w.PilotError("WGC_BUFFER_MISMATCH: incomplete BGRA frame")
    if not (0 <= x and 0 <= y and x + width <= full_width and y + height <= full_height):
        raise w.PilotError("WGC_GEOMETRY_MISMATCH: invalid client crop")
    return b"".join(data[((y + row) * full_width + x) * 4:((y + row) * full_width + x + width) * 4]
                    for row in range(height))


async def capture_async(target):
    (init_apartment, ApartmentType, FramePool, Session, create_for_window,
     PixelFormat, wrap_device, SoftwareBitmap, Buffer) = load_dependencies()
    init_apartment(ApartmentType.MULTI_THREADED)
    if not Session.is_supported():
        raise w.PilotError("WGC_UNSUPPORTED: Windows Graphics Capture unavailable; no fallback")
    geometry = client_geometry(target)
    item = create_for_window(target.hwnd)  # exact HWND only; never monitor/title/desktop selection
    if (item.size.width, item.size.height) != geometry[:2]:
        raise w.PilotError("WGC_GEOMETRY_MISMATCH: capture item differs from target DWM bounds")
    device = make_device(wrap_device)
    pool = session = frame = bitmap = None
    try:
        pool = FramePool.create_free_threaded(device, PixelFormat.B8_G8_R8_A8_UINT_NORMALIZED, 2, item.size)
        session = pool.create_capture_session(item)
        session.is_cursor_capture_enabled = False
        started = time.perf_counter()
        session.start_capture()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            frame = pool.try_get_next_frame()
            if frame is None:
                await asyncio.sleep(0.01)
                continue
            if frame.system_relative_time.total_seconds() < started:
                frame.close()
                frame = None
                continue
            if (frame.content_size.width, frame.content_size.height) != geometry[:2]:
                raise w.PilotError("WGC_RESIZED_DURING_CAPTURE: frame content size changed")
            bitmap = await SoftwareBitmap.create_copy_from_surface_async(frame.surface)
            if (bitmap.pixel_width, bitmap.pixel_height) != geometry[:2]:
                raise w.PilotError("WGC_GEOMETRY_MISMATCH: surface size differs from target")
            buffer = Buffer(geometry[0] * geometry[1] * 4)
            bitmap.copy_to_buffer(buffer)
            data = bytes(buffer)
            if client_geometry(target) != geometry:
                raise w.PilotError("WGC_RESIZED_DURING_CAPTURE: target client geometry changed")
            client = crop_client(data, *geometry)
            return w.png(geometry[4], geometry[5], client)
        raise w.PilotError("WGC_NO_FRESH_FRAME: no frame captured after session start; no fallback")
    finally:
        for value in (bitmap, frame, session, pool, device):
            if value is not None:
                value.close()


def capture_worker(target):
    try:
        return asyncio.run(capture_async(target))
    except w.PilotError:
        raise
    except Exception as exc:
        raise w.PilotError(f"WGC_FAILED: {type(exc).__name__}: {exc}; no fallback") from exc
