"""Real fixture + production connection factory + independent Service/Dispatcher contexts.

No administrator service/IPC/client configuration is installed or used.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot.admin_service import create_connection_service
    from window_pilot.coordination import Coordinator
    from window_pilot.rpc import Dispatcher
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class CoordinationNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            raise unittest.SkipTest("requires interactive local desktop")
        cls.evidence = []

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "config.json"
        self.config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        self.fixture_owner = Service(self.config)
        self.hwnd = self.fixture_owner.call("launch_test", {})["windows"][0]["hwnd"]
        self.now = time.monotonic()
        self.coordinator = Coordinator(clock=lambda: self.now)
        self.clients, self.ids, self.events = {}, {}, []
        self.connect("a"); self.connect("b")

    def connect(self, who):
        service = create_connection_service(self.config, self.root / (who + ".lock"), who, self.coordinator)
        self.assertIs(service.coordinator, self.coordinator)
        dispatch = Dispatcher(service)
        dispatch.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}})
        dispatch.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.clients[who], self.ids[who] = (service, dispatch), 0

    def call(self, who, name, expect=None, **arguments):
        self.ids[who] += 1
        reply = self.clients[who][1].handle({"jsonrpc": "2.0", "id": self.ids[who], "method": "tools/call",
                                           "params": {"name": name, "arguments": arguments}})["result"]
        text = reply["content"][0]["text"]
        if expect:
            self.assertTrue(reply["isError"], text)
            self.assertIn(expect, text)
            self.events.append({"client": who, "refused": expect})
            return text
        self.assertFalse(reply["isError"], text)
        return json.loads(text)

    def bind(self, who, hwnd=None, access="observe_and_mouse"):
        self.call(who, "list_windows")
        return self.call(who, "bind_window", hwnd=hwnd or self.hwnd, access=access,
                         purpose="project-owned shared-window acceptance")["target_id"]

    def control(self, who, token, operation, **args):
        return self.call(who, "window_control", target_id=token, operation=operation, **args)

    def observe(self, who, token):
        return self.call(who, "observe", target_id=token)

    def click(self, who, token, frame, **args):
        return self.call(who, "click", target_id=token, frame_id=frame["frame_id"], x=40, y=40, **args)

    def test_ownership_handoff_and_all_connection_observation_invalidation(self):
        a, b = self.bind("a"), self.bind("b")
        b_controls = self.bind("b", access="observe_and_control")
        self.control("a", a, "acquire")
        owner_frame = self.observe("a", a)
        old_b_frame = self.observe("b", b)
        old_b_tree = self.call("b", "observe_controls", target_id=b_controls)
        self.assertEqual(old_b_tree["status"], "ok", old_b_tree)
        self.assertIn("UIA sample button", {node["name"] for node in old_b_tree["nodes"]}, old_b_tree)
        stages = old_b_tree["worker_diagnostics"]["stages"]
        self.assertTrue(stages)
        self.assertTrue(all(stage["apartment"] == "MTA" for stage in stages))
        self.events.append({"original_worker_uia_stages": stages, "limits": old_b_tree["limits"],
                            "process_elapsed_ms": round((old_b_tree["finished_at"] - old_b_tree["started_at"]) * 1000)})
        self.control("b", b, "acquire", expect="WINDOW_OWNED_BY_ANOTHER_CONNECTION")
        self.click("b", b, old_b_frame, expect="WINDOW_NOT_OWNER")
        self.click("a", a, owner_frame)
        self.observe("a", a)
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        self.assertIn(old_b_frame["frame_id"], self.clients["b"][0].frames)  # cached, but globally invalid
        self.call("b", "observe_controls", target_id=b, frame_id=old_b_frame["frame_id"],
                  expect="WINDOW_OBSERVATION_INVALIDATED")  # input itself, before any handoff
        self.control("a", a, "release")
        self.control("b", b, "acquire")
        self.click("b", b, old_b_frame, expect="WINDOW_OBSERVATION_INVALIDATED")
        button = next(node for node in old_b_tree["nodes"] if node["name"] == "UIA sample button")
        self.call("b", "control_action", target_id=b_controls, observation_id=old_b_tree["observation_id"],
                  control_id=button["control_id"], action="invoke", expect="WINDOW_OBSERVATION_INVALIDATED")
        fresh = self.observe("b", b)
        self.click("b", b, fresh)
        self.observe("b", b)
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=2")
        self.events.append({"cached_old_frame_and_control_refused": True, "actual_clicks_after_handoff": 2})

    def test_failed_uia_read_cannot_acknowledge_unreviewed_input(self):
        from window_pilot import uia
        a, b = self.bind("a"), self.bind("b")
        self.control("a", a, "acquire")
        self.click("a", a, self.observe("a", a))
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        real_observe = uia.observe
        # Real worker, controlled 1ms cutoff; no fake successful tree or review.
        with patch.object(uia, "observe", side_effect=lambda *args: real_observe(*args, timeout=0.001)):
            failed = self.call("a", "observe_controls", target_id=a)
        self.assertEqual(failed["status"], "timeout", failed)
        self.assertTrue(self.control("a", a, "status")["unobserved_input"])
        self.assertTrue(self.control("a", a, "release")["faulted"])
        self.assertTrue(self.control("b", b, "acquire")["faulted"])
        self.click("b", b, self.observe("b", b), expect="WINDOW_INPUT_FAULTED")
        self.events.append({"native_clicks": 1, "controlled_real_worker_timeout": True,
                            "failed_tree_did_not_review_input": True, "handoff_fault_retained": True})

    def test_disconnect_releases_ownership_and_simultaneous_acquire_has_one_winner(self):
        a, b = self.bind("a"), self.bind("b")
        self.control("a", a, "acquire")
        self.clients["a"][0].dispose()
        self.assertTrue(w.U.IsWindow(self.hwnd))  # fixture is owned separately, not by the disconnected client
        self.control("b", b, "acquire")
        self.control("b", b, "release")
        self.connect("c")
        c = self.bind("c")
        barrier = threading.Barrier(2)
        def acquire(who, token):
            barrier.wait(timeout=5)
            self.ids[who] += 1
            return who, self.clients[who][1].handle({"jsonrpc": "2.0", "id": self.ids[who], "method": "tools/call",
                "params": {"name": "window_control", "arguments": {"target_id": token, "operation": "acquire"}}})["result"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [future.result(timeout=10) for future in [pool.submit(acquire, "b", b), pool.submit(acquire, "c", c)]]
        winners = [who for who, result in results if not result["isError"]]
        self.assertEqual(len(winners), 1, results)
        winner = winners[0]; token = b if winner == "b" else c
        self.click(winner, token, self.observe(winner, token))
        self.observe(winner, token)
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        self.events.append({"concurrent_winners": winners, "native_counter": 1, "disconnected_owner_released": True})

    def test_unknown_input_survives_expiry_rebind_disconnect_and_requires_review(self):
        a, b = self.bind("a"), self.bind("b")
        self.control("a", a, "acquire", lease_seconds=10)
        frame = self.observe("a", a)
        old_b = self.observe("b", b)
        real_post = w.post
        def interrupted(hwnd, message, wp=0, lp=0):
            if message == 0x0202:
                raise w.PilotError("controlled missing release")
            return real_post(hwnd, message, wp, lp)
        with patch.object(w, "post", side_effect=interrupted):
            self.click("a", a, frame, expect="POST_DISPATCH_ERROR")
        self.now += 11  # controlled lease expiry, not a real time wait
        self.assertTrue(self.control("b", b, "acquire")["faulted"])
        self.click("b", b, old_b, expect="WINDOW_INPUT_FAULTED")
        rebound = self.bind("b")
        self.click("b", rebound, self.observe("b", rebound), expect="WINDOW_INPUT_FAULTED")
        self.clients["b"][0].dispose()
        self.connect("c")
        c = self.bind("c")
        self.assertTrue(self.control("c", c, "acquire")["faulted"])
        reviewed = self.observe("c", c)
        self.control("c", c, "recover", frame_id=reviewed["frame_id"], purpose="inspect fixture partial input",
                     expect="EXPLICIT_REVIEWED_RECOVERY_REQUIRED")
        recovered = self.control("c", c, "recover", frame_id=reviewed["frame_id"], purpose="inspect fixture partial input",
                                 confirmation="reviewed_effect_no_replay")
        self.assertFalse(recovered["faulted"])
        self.assertNotIn(reviewed["frame_id"], self.clients["c"][0].frames)
        self.click("c", c, self.observe("c", c))
        self.observe("c", c)
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        self.events.append({"fault_survived": ["lease expiry", "new binding", "disconnect", "new connection"],
                            "explicit_review_required": True, "new_post_recovery_clicks": 1})

    def test_inflight_expiry_disconnect_and_different_window_isolation(self):
        other_root = self.root / "other"
        other_root.mkdir()
        config = other_root / "config.json"; config.write_text("{}")
        other = Service(config)
        resume = threading.Event()
        try:
            hwnd2 = other.call("launch_test", {})["windows"][0]["hwnd"]
            a, b, b2 = self.bind("a"), self.bind("b"), self.bind("b", hwnd=hwnd2)
            self.control("a", a, "acquire", lease_seconds=10)
            self.now += 9
            self.control("a", a, "renew", lease_seconds=10)
            self.now += 2
            self.control("b", b, "acquire", expect="WINDOW_OWNED_BY_ANOTHER_CONNECTION")
            self.control("b", b2, "acquire")
            fa, fb2 = self.observe("a", a), self.observe("b", b2)
            entered, real_post = threading.Event(), w.post
            def paused(hwnd, message, wp=0, lp=0):
                result = real_post(hwnd, message, wp, lp)
                if hwnd == self.hwnd and message == 0x0201:
                    entered.set()
                    if not resume.wait(10):
                        raise RuntimeError("fixture pause timeout")
                return result
            with ThreadPoolExecutor(max_workers=1) as pool, patch.object(w, "post", side_effect=paused):
                running = pool.submit(self.click, "a", a, fa)
                try:
                    self.assertTrue(entered.wait(5))
                    self.now += 11
                    self.control("b", b, "acquire", expect="WINDOW_ACTION_IN_FLIGHT")
                    self.click("b", b2, fb2)
                    self.observe("b", b2)
                    self.assertEqual(w.text(hwnd2), "Window Pilot Test | clicks=1")
                    self.clients["a"][0].dispose()
                    self.control("b", b, "acquire", expect="WINDOW_ACTION_IN_FLIGHT")
                finally:
                    resume.set()
                running.result(timeout=10)
            status = self.control("b", b, "acquire")
            self.assertTrue(status["faulted"])  # disconnect before owner observation cannot erase uncertain effects
            self.events.append({"renewal_preserved_ownership": True, "no_inflight_takeover_after_expiry_or_disconnect": True,
                                "different_window_native_clicks": 1, "post_disconnect_fault_retained": True})
        finally:
            resume.set()
            other.dispose()

    def tearDown(self):
        for service, _ in self.clients.values():
            service.dispose()
        self.fixture_owner.call("close_test", {})
        self.fixture_owner.dispose()
        self.temp.cleanup()
        self.evidence.append({"test": self._testMethodName, "layer": "production factory + independent Service/Dispatcher + native fixture; no IPC/admin", "events": self.events})
        destination = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
        if destination:
            path = Path(destination).resolve()
            self.assertTrue(path.is_relative_to(Path(__file__).resolve().parents[1] / ".local"))
            path.mkdir(parents=True, exist_ok=True)
            (path / "coordination-effects.json").write_text(json.dumps(self.evidence, indent=2), encoding="utf8")
