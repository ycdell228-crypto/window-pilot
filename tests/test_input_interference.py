"""External events here are controlled SendInput, never claimed as human hardware.

All real input targets the project fixture. Suspended focus workers are our own
children and are killed by the production probe cleanup.
"""
import ctypes as C
import json
import os
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import patch
import test_foreground as fixture_tests
from window_pilot import foreground as fg, win32 as w
from window_pilot import input_monitor as im


class InterferenceNativeTests(unittest.TestCase):
    setUpClass = classmethod(fixture_tests.ForegroundNativeTests.setUpClass.__func__)
    setUp = fixture_tests.ForegroundNativeTests.setUp
    bind = fixture_tests.ForegroundNativeTests.bind
    frame = fixture_tests.ForegroundNativeTests.frame
    action = fixture_tests.ForegroundNativeTests.action
    tree = fixture_tests.ForegroundNativeTests.tree
    node = fixture_tests.ForegroundNativeTests.node
    point = fixture_tests.ForegroundNativeTests.point
    focus_edit = fixture_tests.ForegroundNativeTests.focus_edit
    save_effect_image = fixture_tests.ForegroundNativeTests.save_effect_image

    @classmethod
    def tearDownClass(cls):
        destination=os.environ.get('WINDOW_PILOT_EVIDENCE_DIR')
        if destination:
            folder=Path(destination).resolve()
            if not folder.is_relative_to(Path(__file__).resolve().parents[1]/'.local'):
                raise AssertionError('private evidence only')
            folder.mkdir(parents=True,exist_ok=True)
            (folder/'interference-effects.json').write_text(json.dumps(cls.evidence,indent=2),encoding='utf8')

    def suspend_probe(self, probe):
        library = C.WinDLL('ntdll')
        w.api(library, 'NtSuspendProcess', C.c_long, w.W.HANDLE)
        w.api(w.K, 'OpenProcess', w.W.HANDLE, w.W.DWORD, w.W.BOOL, w.W.DWORD)
        handle = w.K.OpenProcess(0x0800, False, probe.process.pid)
        w.check(handle, 'open owned focus worker')
        try:
            self.assertEqual(library.NtSuspendProcess(handle), 0)
        finally:
            w.K.CloseHandle(handle)

    def interrupt_while_owned(self, action, parameters, owned, external, cleanup=lambda:None):
        real_read = fg.FocusProbe.read
        monitors = []
        original_monitor = fg.InputMonitor
        reached = threading.Event()
        finished = threading.Event()
        cancelled = threading.Event()
        errors = []
        timing = {}
        def monitor_factory():
            value = original_monitor(); monitors.append(value); return value
        def slow_read(probe, point=None):
            if not reached.is_set() and w.U.GetAsyncKeyState(owned) & 0x8000:
                self.suspend_probe(probe)
                timing['blocked'] = time.monotonic()
                reached.set()
            return real_read(probe, point)
        def intervene():
            try:
                if not reached.wait(15): raise AssertionError('owned fixture input not reached')
                if cancelled.is_set(): return
                self.assertEqual(w.U.GetForegroundWindow(),self.hwnd)
                external()
            except BaseException as exc:
                errors.append(exc)
            finally:
                finished.set()
        thread = threading.Thread(target=intervene)
        thread.start()
        try:
            with patch.object(fg, 'InputMonitor', side_effect=monitor_factory), patch.object(fg.FocusProbe, 'read', slow_read):
                result = self.action(action, **parameters)
            timing['returned'] = time.monotonic()
            self.assertTrue(finished.wait(2)); thread.join(2)
            if errors: raise errors[0]
            self.assertTrue(reached.is_set())
            self.assertEqual(result['status'], 'unknown', result)
            self.assertEqual(result['error'], 'FOREGROUND_EXTERNAL_INPUT', result)
            self.assertLess(timing['returned'] - timing['blocked'], 1.5)
            self.assertTrue(all(value.closed and not value.thread.is_alive() for value in monitors))
            return result, round((timing['returned'] - timing['blocked']) * 1000)
        finally:
            cancelled.set(); reached.set(); finished.wait(2); thread.join(2)
            cleanup()

    def recover_for_next_fixture_case(self):
        frame = self.frame()
        self.a.call('window_control', dict(target_id=self.token, operation='recover', frame_id=frame['frame_id'],
                    purpose='review interrupted project fixture; next independent modifier case', confirmation='reviewed_effect_no_replay'))
        self.frame()

    def test_short_tap_interrupts_slow_probe_releases_ctrl_and_fault_survives_handoff(self):
        def short_tap():
            fg.inject(fg.keyboard(120)); fg.inject(fg.keyboard(120, flags=2))  # F9, no text
        result, elapsed = self.interrupt_while_owned('keys', {'keys':['CTRL','A']}, 162, short_tap)
        self.assertFalse(w.U.GetAsyncKeyState(162) & 0x8000)
        self.assertFalse(w.U.GetAsyncKeyState(120) & 0x8000)
        self.assertEqual(self.node('foreground-echo')['name'], 'Echo: initial')
        self.a.call('window_control', dict(target_id=self.token, operation='release'))
        token = self.bind(self.b, 'observe_and_foreground')
        self.assertTrue(self.b.call('window_control',dict(target_id=token,operation='acquire'))['faulted'])
        frame = self.b.call('observe',dict(target_id=token))
        with self.assertRaisesRegex(w.PilotError, 'WINDOW_INPUT_FAULTED'):
            self.b.call('foreground_action',dict(target_id=token,frame_id=frame['frame_id'],action='keys',keys=['CTRL','A']))
        self.evidence.append(dict(test=self.id(),controlled_external_short_tap=True,slow_owned_worker_suspended=True,
                                 interruption_ms=elapsed,ctrl_released=True,echo_unchanged=True,handoff_fault_retained=True))

    def test_external_mouse_move_stops_drag_and_releases_tool_button(self):
        start = self.point('drag-thumb')
        origin = w.W.POINT(start['x'] + 8, start['y']); w.U.ClientToScreen(self.hwnd, C.byref(origin))
        result, elapsed = self.interrupt_while_owned('drag',dict(**start,end_x=start['x']+120,end_y=start['y'],steps=6),
                                                     1, lambda:fg.inject(fg.mouse(1,origin)))
        self.assertFalse(w.U.GetAsyncKeyState(1) & 0x8000)
        self.assertGreater(result['input_monitor_counts']['external_mouse_move'], 0)
        self.assertNotEqual(self.node('drag-echo')['name'], 'Drag x: 160')
        self.save_effect_image('drag-interrupted.png')
        self.evidence.append(dict(test=self.id(),controlled_external_mouse_move=True,interruption_ms=elapsed,
                                 tool_button_released=True,requested_drag_end_not_reached=True))

    def test_same_and_opposite_modifier_sides_preserve_external_hold(self):
        cases = [('CTRL',162,162),('CTRL',162,163),('SHIFT',160,160),('SHIFT',160,161),('ALT',164,164),('ALT',164,165)]
        outcomes = []
        for index,(name,tool_key,external_key) in enumerate(cases):
            if index: self.recover_for_next_fixture_case()
            with self.subTest(modifier=name,same_side=tool_key==external_key):
                def external(): fg.inject(fg.keyboard(external_key))
                # Leave the external key down until state assertions below; final cleanup is test-owned.
                try:
                    result, elapsed = self.interrupt_while_owned('keys', {'keys':[name,'A']}, tool_key, external)
                    self.assertTrue(w.U.GetAsyncKeyState(external_key) & 0x8000)
                    if tool_key != external_key:
                        self.assertFalse(w.U.GetAsyncKeyState(tool_key) & 0x8000)
                        self.assertEqual(result['release_deferred_count'],0)
                    else:
                        self.assertGreater(result['release_deferred_count'],0)
                    outcomes.append(dict(modifier=name,same_side=tool_key==external_key,external_hold_preserved=True,
                                         opposite_tool_side_released=tool_key!=external_key,interruption_ms=elapsed))
                finally:
                    fg.inject(fg.keyboard(external_key,flags=2))
                    # Only these test-owned states can remain; ensure failure cannot leak a modifier.
                    if w.U.GetAsyncKeyState(tool_key) & 0x8000: fg.inject(fg.keyboard(tool_key,flags=2))
        self.evidence.append(dict(test=self.id(),controlled_synthetic_overlap=outcomes))

    def test_monitor_failure_releases_known_tool_key_without_known_external_hold(self):
        real_read = fg.FocusProbe.read
        def fail_monitor(probe, point=None):
            if w.U.GetAsyncKeyState(162) & 0x8000: probe.monitor.failed = True
            return real_read(probe, point)
        with patch.object(fg.FocusProbe, 'read', fail_monitor):
            result = self.action('keys',keys=['CTRL','A'])
        self.assertEqual(result['status'],'unknown',result)
        self.assertEqual(result['error'],'FOREGROUND_INPUT_MONITOR_UNAVAILABLE')
        self.assertFalse(w.U.GetAsyncKeyState(162) & 0x8000)
        self.assertEqual(result['release_deferred_count'],0)
        self.assertFalse(result['external_input_detected'])
        self.assertFalse(result['owned_input_release_failed'])
        self.assertTrue(result['input_monitor_failed'])
        self.assertFalse(result['input_cleanup_failed'])
        self.assertTrue(self.a.call('window_control',dict(target_id=self.token,operation='status'))['faulted'])
        self.evidence.append(dict(test=self.id(),controlled_monitor_failure_after_real_ctrl_down=True,
                                 actual_ctrl_released=True,unknown_fault_retained=True))

    def test_constructor_interference_and_partial_install_failure_cleanup_hooks(self):
        captured = []
        class Installing(im.InputMonitor):
            def __new__(cls):
                value = super().__new__(cls); captured.append(value); return value
            def check(value):
                fg.inject(fg.keyboard(120)); fg.inject(fg.keyboard(120,flags=2))
                until=time.monotonic()+1
                while not value.interrupted.is_set() and time.monotonic()<until: time.sleep(.005)
                super(Installing,value).check()
        with patch.object(fg, 'InputMonitor', Installing):
            with self.assertRaisesRegex(w.PilotError,'FOREGROUND_EXTERNAL_INPUT') as rejected:
                self.action('keys',keys=['CTRL','A'])
        self.assertEqual(rejected.exception.recovery_diagnostic['attempt_input'],'not_sent')
        self.assertFalse(rejected.exception.recovery_diagnostic['recovery_required'])
        self.assertTrue(captured[0].closed)
        self.assertFalse(captured[0].thread.is_alive())
        self.assertFalse(w.U.GetAsyncKeyState(120) & 0x8000)
        real_install = w.U.SetWindowsHookExW
        captured.clear()
        class Partial(im.InputMonitor):
            def __new__(cls):
                value=super().__new__(cls);captured.append(value);return value
        def fail_mouse(kind,*args):
            return 0 if kind==14 else real_install(kind,*args)
        with patch.object(w.U,'SetWindowsHookExW',side_effect=fail_mouse):
            with self.assertRaisesRegex(im.MonitorError,'MONITOR_UNAVAILABLE'): Partial()
        self.assertTrue(captured[0].closed)
        self.assertFalse(captured[0].thread.is_alive())
        self.evidence.append(dict(test=self.id(),controlled_external_tap_during_constructor=True,
                                 real_partial_hook_install_failure=True,threads_closed=True,not_sent_no_fault=True))

    def test_matching_marker_without_injected_flag_is_still_external_callback_policy(self):
        monitor = im.InputMonitor()
        try:
            event=im.KeyEvent(120,0,0,0,monitor.marker)
            # Explicit callback-policy simulation, not a real hardware event.
            with patch.object(w.U,'CallNextHookEx',return_value=0):
                monitor.keyboard_callback(0,0x100,C.addressof(event))
            self.assertTrue(monitor.interrupted.is_set())
            self.assertIn(120,monitor.external_down)
        finally:monitor.close()
        self.evidence.append(dict(test=self.id(),simulated_callback_noninjected_matching_marker=True,
                                 classified_external=True,not_hardware_evidence=True))
