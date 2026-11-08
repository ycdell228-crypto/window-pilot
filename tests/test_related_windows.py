"""Owner relationships: controlled cycles and real nonactivating owned windows."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class OwnerChainTests(unittest.TestCase):
    def test_cycle_does_not_hang_or_return_invented_relationship(self):
        with patch.object(w.U, "GetWindow", side_effect=lambda hwnd, flag: {1: 2, 2: 1}[hwnd]):
            with self.assertRaisesRegex(w.PilotError, "WINDOW_OWNER_CYCLE"):
                w.owner_chain(1)


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class RelatedWindowNativeTests(unittest.TestCase):
    def test_owned_nested_and_unrelated_windows_and_explicit_binding(self):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            self.skipTest("requires interactive local desktop")
        create = w.api(w.U, "CreateWindowExW", w.W.HWND, w.W.DWORD, w.W.LPCWSTR, w.W.LPCWSTR,
                       w.W.DWORD, w.C.c_int, w.C.c_int, w.C.c_int, w.C.c_int,
                       w.W.HWND, w.W.HMENU, w.W.HINSTANCE, w.PTR)
        destroy = w.api(w.U, "DestroyWindow", w.W.BOOL, w.W.HWND)
        enable = w.api(w.U, "EnableWindow", w.W.BOOL, w.W.HWND, w.W.BOOL)
        handles = []
        def make(title, owner=None):
            hwnd = create(0x08000000, "STATIC", title, 0x10CF0000,
                          120, 120, 240, 160, owner, None, None, None)
            self.assertTrue(hwnd)
            handles.append(hwnd)
            return hwnd
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text('{}')
            service = Service(config)
            try:
                main = make("WP relation main")
                popup = make("WP relation owned", main)
                nested = make("WP relation nested", popup)
                unrelated = make("WP relation unrelated")
                enable(main, False)
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": main})["target_id"]
                result = service.call("list_windows", {"target_id": token})
                rows = {row["hwnd"]: row for row in result["windows"]}
                self.assertEqual(set(rows), {popup, nested})
                self.assertNotIn(unrelated, rows)
                self.assertFalse(result["target_enabled"])
                self.assertTrue(rows[popup]["may_block_target"])
                self.assertEqual(rows[nested]["owner_chain"], [popup, main])
                self.assertEqual(rows[popup]["relationship"], "owned_descendant")
                self.assertEqual(set(service.targets), {token})  # discovery never auto-binds
                popup_token = service.call("bind_window", {"hwnd": popup})["target_id"]
                self.assertEqual(service.bindings[popup_token]["access"], "observe")
                owner_rows = service.call("list_windows", {"target_id": popup_token})["windows"]
                self.assertEqual(next(row["relationship"] for row in owner_rows if row["hwnd"] == main), "owner")
                self.assertNotIn(int(w.U.GetForegroundWindow() or 0), handles)
                # A destroyed popup cannot be automatically resurrected from discovery.
                destroy(nested)
                handles.remove(nested)
                service.call("list_windows", {"target_id": token})
                with self.assertRaisesRegex(w.PilotError, "WINDOW_NOT_RECENTLY_LISTED"):
                    service.call("bind_window", {"hwnd": nested})
                evidence = Path(__file__).resolve().parents[1] / ".local/related-windows"
                evidence.mkdir(exist_ok=True)
                (evidence / "native.json").write_text(json.dumps(result, indent=2), encoding="utf8")
            finally:
                service.dispose()
                for hwnd in reversed(handles):
                    destroy(hwnd)
