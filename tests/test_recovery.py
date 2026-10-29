"""Recovery workflow through production Service/Dispatcher and project-owned fixtures.

Controlled dispatch/provider failures are labelled; successful clicks use real messages.
No installed executor, user application, or global input is used.
"""
import json
import base64
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

if sys.platform == "win32":
    from window_pilot import win32 as w
    from window_pilot import uia
    from window_pilot.admin_service import create_connection_service
    from window_pilot.coordination import Coordinator
    from window_pilot.rpc import Dispatcher
    from window_pilot.service import Service


@unittest.skipUnless(sys.platform == "win32", "requires Windows")
class RecoveryNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1") or not w.U.GetForegroundWindow():
            raise unittest.SkipTest("requires interactive local desktop")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        config = self.root / "config.json"
        config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        self.fixture = Service(config)
        self.hwnd = self.fixture.call("launch_test", {})["windows"][0]["hwnd"]
        self.coordinator = Coordinator()
        self.services = {name: create_connection_service(config, self.root / (name + ".lock"), name, self.coordinator)
                         for name in ("a", "b")}
        self.dispatchers = {name: Dispatcher(service) for name, service in self.services.items()}
        self.sequence = 0
        self.tokens = {name: self.bind(name) for name in self.services}
        self.events = []

    def call(self, who, name, error=None, **arguments):
        self.sequence += 1
        reply = self.dispatchers[who].handle({"jsonrpc":"2.0", "id":self.sequence, "method":"tools/call",
                                            "params":{"name":name, "arguments":arguments}})["result"]
        if error:
            self.assertTrue(reply["isError"], reply)
            self.assertIn(error, reply["content"][0]["text"])
            return json.loads(reply["content"][1]["text"])["recovery_diagnostic"]
        self.assertFalse(reply["isError"], reply)
        data = json.loads(reply["content"][0]["text"])
        if any(item["type"] == "image" for item in reply["content"]):
            data["delivered_image"] = True
            self.last_image = next(item["data"] for item in reply["content"] if item["type"] == "image")
        return data

    def save_image(self, name):
        destination = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
        if destination:
            folder = Path(destination).resolve()
            self.assertTrue(folder.is_relative_to(Path(__file__).resolve().parents[1] / ".local"))
            folder.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(base64.b64decode(self.last_image))

    def bind(self, who, access="observe_and_mouse"):
        self.call(who, "list_windows")
        return self.call(who, "bind_window", hwnd=self.hwnd, access=access,
                         purpose="review project-owned fixture input", capture_backend="printwindow")["target_id"]

    def control(self, who, operation, **args):
        return self.call(who, "window_control", target_id=self.tokens[who], operation=operation, **args)

    def observe(self, who):
        return self.call(who, "observe", target_id=self.tokens[who])

    def click(self, who, frame, **kwargs):
        return self.call(who, "click", target_id=self.tokens[who], frame_id=frame["frame_id"], x=40, y=40, **kwargs)

    def partial_input(self):
        self.control("a", "acquire")
        frame = self.observe("a")
        native_post = w.post
        def missing_release(hwnd, message, wp=0, lp=0):
            if message == 0x0202:
                raise w.PilotError("controlled missing release")
            return native_post(hwnd, message, wp, lp)
        with patch.object(w, "post", side_effect=missing_release):
            diagnostic = self.click("a", frame, error="POST_DISPATCH_ERROR")
        self.assertEqual(diagnostic["attempt_input"], "partial_or_unknown")
        self.assertTrue(diagnostic["recovery_required"])
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=0")
        return diagnostic

    def submit(self, who, plan, **changes):
        args = {**plan["arguments"], **changes}
        return self.call(who, plan["name"], **args)

    def test_proven_not_sent_refusal_needs_no_recovery_and_new_action_works(self):
        self.control("a", "acquire")
        frame = self.observe("a")
        denied = self.call("a", "click", target_id=self.tokens["a"], frame_id=frame["frame_id"],
                           x=-1, y=40, error="INVALID_POINT")
        self.assertEqual(denied["attempt_input"], "not_sent")
        self.assertFalse(denied["recovery_required"])
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=0")
        self.assertEqual(self.control("a", "prepare_recovery")["preparation"], "not_required")
        self.click("a", self.observe("a"))
        pending = self.control("a", "status")
        self.assertEqual(pending["input_state"], "sent_unreviewed")
        ready = self.control("a", "prepare_recovery")
        self.assertEqual(ready["preparation"], "assess_observation")
        self.assertIsNone(ready["next_call_after_review"])
        self.assertTrue(ready["delivered_image"])
        self.assertFalse(ready["diagnostic"]["recovery_required"])
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        self.events.append({"proven_not_sent_no_recovery":True, "actual_clicks_after_new_action":1,
                            "prepared_read_did_not_replay":True})

    def test_partial_input_prepare_review_commit_and_new_observation_without_replay(self):
        self.partial_input()
        prepared = self.control("a", "prepare_recovery")
        self.assertEqual(prepared["preparation"], "review_required")
        self.assertTrue(prepared["delivered_image"])
        self.save_image("partial-prepared-before.png")
        self.assertTrue(self.control("a", "status")["faulted"])
        proof = prepared["evidence"]
        self.click("a", proof, error="WINDOW_INPUT_FAULTED")
        recovered = self.submit("a", prepared["next_call_after_review"])
        self.assertFalse(recovered["faulted"])
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=0")
        self.click("a", proof, error="STALE_FRAME")
        fresh = self.submit("a", recovered["next_call"])
        self.click("a", fresh)
        self.observe("a")
        self.save_image("partial-after-new-action.png")
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        self.events.append({"controlled_missing_release":True, "actual_clicks_before_recovery":0,
                            "after_recovery":0, "after_explicit_new_action":1})

    def test_sent_unreviewed_handoff_and_reuse_of_successful_current_evidence(self):
        self.control("a", "acquire")
        self.click("a", self.observe("a"))
        self.control("a", "release")
        pending = self.control("b", "status")
        self.assertEqual(pending["input_state"], "sent_unreviewed")
        self.assertTrue(pending["faulted"])
        prepared = self.control("b", "prepare_recovery")
        reused = self.control("b", "prepare_recovery", frame_id=prepared["evidence"]["frame_id"])
        self.assertTrue(reused["evidence"]["reused"])
        self.submit("b", reused["next_call_after_review"])
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        self.events.append({"actual_sent_unreviewed_clicks":1, "handoff_requires_review":True,
                            "same_owner_current_evidence_reused":True, "actual_clicks_after_recovery":1})

    def test_lease_expiry_during_acquisition_uses_new_fault_for_preparation(self):
        now = [time.monotonic()]
        self.coordinator.clock = lambda: now[0]
        self.control("a", "acquire", lease_seconds=10)
        self.click("a", self.observe("a"))
        actual_acquire = self.coordinator.acquire
        def expire_before_acquiring(*args, **kwargs):
            now[0] += 11  # controlled lease boundary; real Coordinator performs expiry/handoff
            return actual_acquire(*args, **kwargs)
        with patch.object(self.coordinator, "acquire", side_effect=expire_before_acquiring):
            prepared = self.control("b", "prepare_recovery")
        self.assertFalse(prepared["diagnostic_before"]["faulted"])
        self.assertTrue(prepared["diagnostic"]["faulted"])
        self.assertEqual(prepared["preparation"], "review_required")
        recovered = self.submit("b", prepared["next_call_after_review"])
        self.assertFalse(recovered["faulted"])
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        self.events.append({"controlled_lease_boundary_before_real_acquire":True,
                            "new_unreviewed_fault_prepared":True, "actual_clicks_unchanged":1})

    def test_successful_real_controls_can_prepare_and_commit_recovery(self):
        self.partial_input()
        prepared = self.control("a", "prepare_recovery", evidence_kind="controls")
        self.assertEqual(prepared["preparation"], "review_required")
        self.assertEqual(prepared["evidence"]["status"], "ok")
        self.assertIn("UIA sample button", {node["name"] for node in prepared["evidence"]["nodes"]})
        # Move only our own fixture without activation; old UIA screen geometry
        # must no longer be accepted as recovery evidence.
        rectangle = w.W.RECT()
        w.check(w.U.GetWindowRect(self.hwnd, w.C.byref(rectangle)), "own fixture rectangle")
        w.api(w.U, "SetWindowPos", w.W.BOOL, w.W.HWND, w.W.HWND, w.C.c_int, w.C.c_int, w.C.c_int, w.C.c_int, w.W.UINT)
        w.check(w.U.SetWindowPos(self.hwnd, None, rectangle.left + 2, rectangle.top, 0, 0, 0x15), "move own fixture")
        self.submit("a", prepared["next_call_after_review"], error="RECOVERY_FRESH_OBSERVATION_REQUIRED")
        prepared = self.control("a", "prepare_recovery", evidence_kind="controls")
        recovered = self.submit("a", prepared["next_call_after_review"])
        self.assertFalse(recovered["faulted"])
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=0")
        fresh = self.submit("a", recovered["next_call"])
        self.click("a", fresh)
        self.observe("a")
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=1")
        self.events.append({"real_nonempty_uia_evidence":True, "moved_fixture_old_geometry_refused":True, "recovery_did_not_input":True,
                            "actual_clicks_after_new_action":1})

    def test_failed_and_empty_reads_cannot_clear_fault_or_create_recovery_plan(self):
        self.partial_input()
        with patch.object(w, "capture", side_effect=w.PilotError("controlled capture unavailable")):
            failed = self.control("a", "prepare_recovery", error="controlled capture unavailable")
        self.assertTrue(failed["faulted"])
        real_observe = uia.observe
        with patch.object(uia, "observe", side_effect=lambda *args: real_observe(*args, timeout=0.001)):
            timeout = self.control("a", "prepare_recovery", evidence_kind="controls")
        self.assertEqual(timeout["preparation"], "evidence_unavailable")
        self.assertTrue(timeout["diagnostic"]["faulted"])
        with patch.object(uia, "observe", return_value={"status":"ok", "nodes":[], "geometry":{}, "limits":{}}):
            empty = self.control("a", "prepare_recovery", evidence_kind="controls")
        self.assertEqual(empty["preparation"], "evidence_unavailable")
        self.assertTrue(empty["diagnostic"]["faulted"])
        self.assertNotIn("next_call_after_review", empty)
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=0")
        self.events.append({"controlled_capture_failure":True, "controlled_real_worker_1ms_timeout":True,
                            "controlled_empty_provider":True, "fault_retained":True})

    def test_evidence_owner_epoch_expiry_and_read_only_scope_are_enforced(self):
        self.partial_input()
        prepared = self.control("a", "prepare_recovery")
        plan = prepared["next_call_after_review"]
        self.submit("b", plan, target_id=self.tokens["b"], error="RECOVERY_FRESH_OBSERVATION_REQUIRED")
        other_proof = self.observe("b")
        self.control("b", "recover", frame_id=other_proof["frame_id"], purpose="review fixture",
                     confirmation="reviewed_effect_no_replay", error="WINDOW_NOT_OWNER")
        self.services["a"].frames[prepared["evidence"]["frame_id"]]["time"] -= 31
        self.submit("a", plan, error="RECOVERY_FRESH_OBSERVATION_REQUIRED")
        prepared = self.control("a", "prepare_recovery")
        plan = prepared["next_call_after_review"]
        self.control("a", "release")
        self.submit("a", plan, error="WINDOW_OBSERVATION_INVALIDATED")
        read_only = self.bind("b", "observe")
        self.call("b", "window_control", target_id=read_only, operation="prepare_recovery", error="WINDOW_WRITE_BINDING_REQUIRED")
        self.call("b", "window_control", target_id=read_only, operation="recover", frame_id=prepared["evidence"]["frame_id"],
                  purpose="review fixture", confirmation="reviewed_effect_no_replay", error="WINDOW_WRITE_BINDING_REQUIRED")
        self.assertTrue(self.control("b", "status")["faulted"])
        self.assertEqual(w.text(self.hwnd), "Window Pilot Test | clicks=0")
        self.events.append({"cross_connection_evidence_rejected":True, "controlled_31s_old_evidence_rejected":True,
                            "current_proof_nonowner_rejected":True, "handoff_epoch_rejected":True, "read_only_recovery_denied":True})

    def test_diagnostic_and_audit_do_not_store_text_keys_or_uia_value(self):
        token = self.tokens["a"]
        frame = self.observe("a")
        secret = "fixture-private-text-8285"
        self.call("a", "foreground_action", target_id=token, frame_id=frame["frame_id"], action="text", text=secret,
                  error="FOREGROUND_SCOPE_REQUIRED")
        self.call("a", "foreground_action", target_id=token, frame_id=frame["frame_id"], action="keys", keys=["CTRL","Z"],
                  error="FOREGROUND_SCOPE_REQUIRED")
        self.call("a", "control_action", target_id=token, observation_id="old", control_id="old:0", action="set_value", value=secret,
                  error="UIA_CONTROL_ACCESS_REQUIRED")
        audit = (self.root / ".local/audit.jsonl").read_text(encoding="utf8")
        self.assertNotIn(secret, audit)
        rows = [json.loads(line) for line in audit.splitlines()]
        self.assertTrue(all("keys" not in row.get("arguments", {}) and "text" not in row.get("arguments", {}) and
                            "value" not in row.get("arguments", {}) for row in rows))
        self.events.append({"text_key_sequence_and_uia_value_redacted":True, "no_global_input":True})

    def tearDown(self):
        for service in self.services.values():
            service.dispose()
        self.fixture.dispose()
        destination = os.environ.get("WINDOW_PILOT_EVIDENCE_DIR")
        if destination:
            folder = Path(destination).resolve()
            project = Path(__file__).resolve().parents[1]
            self.assertTrue(folder.is_relative_to(project / ".local"))
            folder.mkdir(parents=True, exist_ok=True)
            (folder / (self.id().split(".")[-1] + ".json")).write_text(json.dumps(self.events,indent=2),encoding="utf8")
        self.temp.cleanup()
