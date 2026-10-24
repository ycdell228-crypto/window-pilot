"""Narrow regressions for window-only backend selection and client crop."""
import struct
import sys
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot import wgc


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class CaptureBackendTests(unittest.TestCase):
    def test_unknown_backend_is_rejected_before_any_capture(self):
        with self.assertRaisesRegex(w.PilotError, "UNKNOWN_CAPTURE_BACKEND"), patch.object(w.subprocess, "run") as run:
            try:
                w.capture(None, backend="screen")
            finally:
                run.assert_not_called()

    def test_client_crop_contains_only_requested_window_pixels(self):
        pixels = b"".join(bytes([i, i, i, 255]) for i in range(12))
        self.assertEqual(wgc.crop_client(pixels, 4, 3, 1, 1, 2, 2),
                         b"".join(bytes([i, i, i, 255]) for i in (5, 6, 9, 10)))

    def test_partial_buffer_and_out_of_bounds_crop_fail(self):
        with self.assertRaisesRegex(w.PilotError, "BUFFER_MISMATCH"):
            wgc.crop_client(b"", 4, 3, 0, 0, 1, 1)
        with self.assertRaisesRegex(w.PilotError, "GEOMETRY_MISMATCH"):
            wgc.crop_client(bytes(48), 4, 3, 3, 0, 2, 1)

    def test_wgc_failure_never_retries_printwindow(self):
        target = w.Identity(1, 2, 3, "test.exe", 4, "test")
        failed = w.subprocess.CompletedProcess([], 1, b"", b"WGC_NO_FRESH_FRAME")
        with patch.object(w, "verify"), patch.object(w, "desktop_state", return_value={}), patch.object(w.subprocess, "run", return_value=failed) as run:
            with self.assertRaisesRegex(w.PilotError, "WGC_NO_FRESH_FRAME"):
                w.capture(target, backend="wgc")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0][-2:], ["--backend", "wgc"])
