"""A project-owned child without a window must not survive service disposal."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows service")
class FixtureCleanupTests(unittest.TestCase):
    def test_own_child_without_a_ready_window_is_terminated_on_dispose(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            config.write_text("{}")
            service = Service(config)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], creationflags=subprocess.CREATE_NO_WINDOW)
            service.fixture = child
            try:
                # Observed startup-failure state: own child exists, no discoverable window.
                with patch.object(service, "fixture_windows", return_value=[]):
                    service.dispose()
                self.assertIsNotNone(child.poll())
            finally:
                if child.poll() is None:
                    child.terminate()
                child.wait(timeout=5)
                service.dispose()
