"""Shared stop contracts, actual worker cleanup, no user desktop input."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import win32 as w, uia
    from window_pilot.coordination import Coordinator, CoordinationError
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class InputStopTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.coordinator = Coordinator(shared=True)
        self.services = []
        for name in ("a", "b"):
            folder = Path(self.temp.name) / name
            folder.mkdir()
            config = folder / "config.json"
            config.write_text('{"tools":{"profile":"legacy","self_test":true}}')
            self.services.append(Service(config, coordinator=self.coordinator, connection_id=name))
        self.target = w.Identity(123, 45, 67, "fixture.exe", 89, "Fixture")

    def tearDown(self):
        for service in self.services:
            service.dispose()
        self.temp.cleanup()

    def stop(self):
        return self.services[0].call("input_control", {"operation": "stop"})

    def resume(self, stop_id):
        return self.services[1].call("input_control", {"operation": "resume", "stop_id": stop_id,
                 "confirmation": "user_requested_resume", "purpose": "explicit fixture continuation"})

    def test_shared_stop_is_idempotent_and_new_input_is_refused(self):
        first = self.stop()
        repeated = self.stop()
        self.assertTrue(first["created_by_this_call"])
        self.assertFalse(repeated["created_by_this_call"])
        self.assertEqual(first["stop_id"], repeated["stop_id"])
        self.assertTrue(self.services[1].call("input_control", {"operation": "status"})["stopped"])
        for service in self.services:
            with self.assertRaisesRegex(CoordinationError, "EXECUTOR_STOPPED"):
                service.call("launch_test", {})
            with self.assertRaisesRegex(CoordinationError, "EXECUTOR_STOPPED"):
                service.call("click", {"target_id": "any", "frame_id": "any", "x": 1, "y": 1})
            self.assertIsNone(service.fixture)
        self.services[0].dispose()
        self.assertTrue(self.services[1].call("input_control", {"operation": "status"})["stopped"])

    def test_stop_receipt_keeps_own_id_when_cancel_callback_replaces_stop(self):
        c = self.coordinator
        stopped_before_resume = None
        replacement = None
        exited = False

        def cancel():
            nonlocal stopped_before_resume, replacement, exited
            if exited:
                return
            exited = True
            stopped_before_resume = c.stop_status()["stop_id"]
            c.resume_input(stopped_before_resume)
            replacement = c.stop_input()

        c.register_browser("own-receipt-fixture", cancel, lambda: exited)
        receipt = self.stop()
        self.assertTrue(receipt["created_by_this_call"])
        self.assertTrue(receipt["stopped"])
        self.assertEqual(receipt["stop_id"], stopped_before_resume)
        self.assertTrue(replacement["created_by_this_call"])
        self.assertNotEqual(receipt["stop_id"], replacement["stop_id"])
        self.assertEqual(c.stop_status()["stop_id"], replacement["stop_id"])
        with self.assertRaisesRegex(CoordinationError, "STOP_ID_MISMATCH"):
            self.resume(receipt["stop_id"])
        self.assertTrue(c.stop_status()["stopped"])

    def test_resume_requires_current_id_and_new_observations(self):
        c = self.coordinator
        c.acquire("a", self.target)
        old = c.observe_begin(self.target)
        stopped = self.stop()
        with self.assertRaisesRegex(CoordinationError, "WINDOW_OBSERVATION_INVALIDATED"):
            c.validate_stamp(self.target, old)
        while_stopped = c.observe_begin(self.target)
        c.observe_end("a", self.target, while_stopped)
        with self.assertRaisesRegex(CoordinationError, "EXPLICIT_USER_RESUME_REQUIRED"):
            self.services[1].call("input_control", {"operation": "resume", "stop_id": stopped["stop_id"]})
        with self.assertRaisesRegex(CoordinationError, "STOP_ID_MISMATCH"):
            self.resume("wrong")
        self.assertFalse(self.resume(stopped["stop_id"])["stopped"])
        with self.assertRaisesRegex(CoordinationError, "WINDOW_OBSERVATION_INVALIDATED"):
            c.validate_stamp(self.target, while_stopped)
        fresh = c.observe_begin(self.target)
        with c.command("a", self.target) as ticket:
            c.begin_input(ticket, self.target, fresh)
            ticket.outcome(sent=False)
        next_stop = self.stop()
        self.assertNotEqual(next_stop["stop_id"], stopped["stop_id"])
        with self.assertRaisesRegex(CoordinationError, "STOP_ID_MISMATCH"):
            self.resume(stopped["stop_id"])

    def test_stop_during_input_cannot_resume_early_or_clear_unknown_fault(self):
        c = self.coordinator
        c.acquire("a", self.target)
        stamp = c.observe_begin(self.target)
        with c.command("a", self.target) as ticket:
            c.begin_input(ticket, self.target, stamp)
            stopped = self.stop()
            self.assertEqual(stopped["in_flight"], 1)
            with self.assertRaisesRegex(CoordinationError, "STOP_STILL_IN_FLIGHT"):
                self.resume(stopped["stop_id"])
            ticket.outcome(sent=True, unknown=True)
        self.resume(stopped["stop_id"])
        self.assertTrue(c.status("a", self.target)["faulted"])
        with self.assertRaisesRegex(CoordinationError, "WINDOW_INPUT_FAULTED"):
            with c.command("a", self.target):
                self.fail("unknown input allowed")

    def test_real_worker_preserves_stdin_and_result(self):
        result = uia.run_action_worker([sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"],
                                       b"bounded fixture", 3, self.coordinator.ensure_running)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"bounded fixture")

    def test_real_started_worker_is_reaped_after_stop(self):
        marker = Path(self.temp.name) / "worker-ready"
        process_list = []
        real_popen = uia.subprocess.Popen
        def spawn(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            process_list.append(process)
            return process
        def check():
            if marker.exists():
                self.coordinator.stop_input()
            self.coordinator.ensure_running()
        code = "import pathlib,sys,time; sys.stdin.buffer.read(); pathlib.Path(sys.argv[1]).write_text('ready'); time.sleep(30)"
        with patch.object(uia.subprocess, "Popen", side_effect=spawn):
            with self.assertRaisesRegex(ValueError, "UIA_WORKER_STOPPED_OUTCOME_UNKNOWN"):
                uia.run_action_worker([sys.executable, "-c", code, str(marker)], b"{}", 5, check)
        self.assertTrue(marker.exists())
        self.assertEqual(len(process_list), 1)
        self.assertIsNotNone(process_list[0].poll())


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class InputStopNativeTests(unittest.TestCase):
    def test_stop_read_resume_and_cancel_real_uia_worker(self):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            self.skipTest("requires interactive local desktop")
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text('{"tools":{"profile":"legacy","self_test":true}}')
            c = Coordinator(shared=True)
            service = Service(config, coordinator=c, connection_id="native-stop")
            try:
                hwnd = service.call("launch_test", {"kind": "uia"})["windows"][0]["hwnd"]
                service.call("list_windows", {})
                token = service.call("bind_window", {"hwnd": hwnd, "access": "observe_and_control",
                            "purpose": "own fixture stop acceptance"})["target_id"]
                service.call("window_control", {"target_id": token, "operation": "acquire"})
                stop = service.call("input_control", {"operation": "stop"})
                tree = service.call("get_window_state", {"target_id": token, "include_screenshot": False})["accessibility"]
                self.assertEqual(tree["status"], "ok")
                node = next(n for n in tree["nodes"] if n["automation_id"] == "value-field")
                args = {"target_id": token, "observation_id": tree["observation_id"], "control_id": node["control_id"],
                        "action": "set_value", "value": "stop fixture new value"}
                with self.assertRaisesRegex(CoordinationError, "EXECUTOR_STOPPED"):
                    service.call("control_action", args)
                service.call("input_control", {"operation": "resume", "stop_id": stop["stop_id"],
                    "confirmation": "user_requested_resume", "purpose": "own fixture continuation"})
                with self.assertRaisesRegex(CoordinationError, "WINDOW_OBSERVATION_INVALIDATED"):
                    service.call("control_action", args)
                tree = service.call("observe_controls", {"target_id": token})
                node = next(n for n in tree["nodes"] if n["automation_id"] == "value-field")
                args.update(observation_id=tree["observation_id"], control_id=node["control_id"])
                # Do not execute SetValue as a success probe: this provider was observed to activate
                # its window. Here the worker is stopped immediately after creation, before stdin.
                popen = uia.subprocess.Popen
                workers = []
                def spawn_then_stop(*a, **kw):
                    process = popen(*a, **kw)
                    workers.append(process)
                    c.stop_input()
                    return process
                with patch.object(uia.subprocess, "Popen", side_effect=spawn_then_stop):
                    result = service.call("control_action", args)
                self.assertEqual(result["status"], "unknown", result)
                self.assertTrue(service.faulted)
                self.assertEqual(len(workers), 1)
                self.assertIsNotNone(workers[0].poll())
                self.assertNotEqual(int(w.U.GetForegroundWindow() or 0), hwnd)
            finally:
                service.dispose()
