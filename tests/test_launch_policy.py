"""Launch restrictions precede durable claims and process creation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import app_launch, win32 as w
    from window_pilot.admin_service import create_connection_service
    from window_pilot.coordination import Coordinator


@unittest.skipUnless(sys.platform == "win32", "requires Windows executable path validation")
class LaunchPolicyTests(unittest.TestCase):
    def test_default_and_explicit_empty_allowlist_are_distinct(self):
        executable = str(Path(sys.executable).resolve())
        app_launch.LaunchPolicy({}).check(executable)
        app_launch.LaunchPolicy({"allowlist": [executable]}).check(executable.upper())
        with self.assertRaisesRegex(w.PilotError, "NOT_ALLOWLISTED"):
            app_launch.LaunchPolicy({"allowlist": []}).check(executable)

    def test_disabled_and_denied_launch_never_reserve_id_or_spawn(self):
        for policy, error in (({"enabled": False}, "DISABLED"), ({"allowlist": []}, "NOT_ALLOWLISTED")):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = root / "config.json"
                config.write_text(json.dumps({"app_launch": policy}))
                service = create_connection_service(config, root / "connection.lock", "policy-test", Coordinator(shared=True))
                marker = root / "unexpected-launch.txt"
                arguments = {"exe": sys.executable, "args": ["-c", "from pathlib import Path; Path(" + repr(str(marker)) + ").write_text('unexpected')"],
                             "purpose": "policy regression in own temp directory", "request_id": "blocked"}
                # Only substitute privilege lookup. The policy and launch path remain real.
                # If the guard is missing, harmless ordinary Python can write this marker.
                try:
                    with patch.object(w, "input_integrity", return_value=0x3000), self.assertRaisesRegex(w.PilotError, error):
                        service.call("launch_app", arguments)
                    self.assertFalse(marker.exists())
                    self.assertFalse((root / ".local/app-launches").exists())
                finally:
                    service.dispose()

    def test_restriction_checked_before_reusing_receipts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = root / "keep.json"
            receipt.write_text("durable claim")
            args = {"exe": sys.executable, "purpose": "test", "request_id": "previous"}
            with patch.object(w, "input_integrity", return_value=0x3000), self.assertRaisesRegex(w.PilotError, "NOT_ALLOWLISTED"):
                app_launch.launch(args, root, app_launch.LaunchPolicy({"allowlist": []}))
            self.assertEqual(receipt.read_text(), "durable claim")
            self.assertEqual(list(root.iterdir()), [receipt])

    def test_invalid_policy_does_not_fall_back_to_unrestricted(self):
        for value in (None, {"enabled": "false"}, {"allowlist": None}, {"allowlist": "python.exe"}, {"allowilst": []}):
            with self.subTest(value=value), self.assertRaises(w.PilotError):
                app_launch.LaunchPolicy(value)
