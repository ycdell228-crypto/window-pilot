"""Own nonactivating fixture acceptance through public MCP dispatch and stdio."""
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
EVIDENCE = Path(os.environ.get('WINDOW_PILOT_WORKFLOW_EVIDENCE_DIR',
                              PROJECT / '.local/window-workflow-test')).resolve()
if not EVIDENCE.is_relative_to(PROJECT / '.local'):
    raise ValueError('workflow evidence must remain inside project .local')

if sys.platform == 'win32':
    from window_pilot import win32 as w
    from window_pilot.service import Service
    from window_pilot.coordination import Coordinator
    from window_pilot.rpc import Dispatcher


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class WindowWorkflowNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('CI') and os.environ.get('WINDOW_PILOT_NATIVE_TESTS') != '1':
            raise unittest.SkipTest('interactive own-fixture evidence is opt-in')
        if not w.U.GetForegroundWindow():
            raise unittest.SkipTest('no interactive desktop')

    def setUp(self):
        self.root = EVIDENCE / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=True)
        self.config = self.root / 'config.json'
        self.config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        self.owner = Service(self.config, self.root / 'fixture.lock')
        self.hwnd = self.owner.call('launch_test', {})['windows'][0]['hwnd']
        self.now = time.monotonic()
        self.coordinator = Coordinator(clock=lambda: self.now)
        self.services = []
        self.events = []
        self.sequence = 0
        self.a = self.connect('a')
        self.b = self.connect('b')

    def connect(self, name):
        service = Service(self.config, self.root / (name + '.lock'),
                          coordinator=self.coordinator, connection_id=name)
        self.services.append(service)
        return service, Dispatcher(service)

    def tearDown(self):
        for service in self.services:
            service.dispose()
        self.owner.dispose()
        self.events.append({'fixture_pid': self.owner.fixture.pid,
                            'fixture_exit_code': self.owner.fixture.poll(),
                            'fixture_window_closed': not bool(w.U.IsWindow(self.hwnd))})
        (self.root / 'events.json').write_text(json.dumps(self.events, indent=2), encoding='utf8')
        self.assertIsNotNone(self.owner.fixture.poll(), 'own fixture process survived disposal')

    def call(self, client, name, expect=None, **args):
        self.sequence += 1
        response = client[1].handle({'jsonrpc': '2.0', 'id': self.sequence,
                                    'method': 'tools/call',
                                    'params': {'name': name, 'arguments': args}})['result']
        text = response['content'][0]['text']
        self.events.append({'tool': name, 'isError': response['isError'], 'text': text})
        if expect:
            self.assertTrue(response['isError'], text)
            self.assertIn(expect, text)
            return text
        self.assertFalse(response['isError'], text)
        value = json.loads(text)
        for content in response['content'][1:]:
            if content['type'] == 'image':
                image = base64.b64decode(content['data'], validate=True)
                self.assertEqual(image[:8], b'\x89PNG\r\n\x1a\n')
                (self.root / f'{self.sequence}.png').write_bytes(image)
        return value

    def begin(self, client=None, access='observe_and_click', expect=None):
        return self.call(client or self.a, 'begin_window_session', expect=expect,
                         hwnd=self.hwnd, access=access, purpose='own fixture workflow acceptance',
                         capture_backend='printwindow')

    def step(self, session, client=None, **extra):
        args = dict(session_id=session['session_id'], state_id=session['state_id'],
                    tool='click', action_args={'x': 40, 'y': 40})
        args.update(extra)
        return self.call(client or self.a, 'act_and_observe', **args)

    def test_single_action_stale_credentials_and_end(self):
        state = self.begin()
        self.assertFalse(state['effect_verified'])
        self.assertEqual(state['state']['status'], 'ok')
        self.assertTrue(state['state']['accessibility']['nodes'])
        self.assertNotIn('image', state['state'])
        self.assertEqual(self.step(state, action_args={'target_id': 'override'},
                                   expect='WORKFLOW_CREDENTIAL_OVERRIDE_REFUSED').split(':')[0],
                         'WORKFLOW_CREDENTIAL_OVERRIDE_REFUSED')
        for credential in ('frame_id', 'observation_id'):
            self.step(state, action_args={credential: 'override'}, expect='WORKFLOW_CREDENTIAL_OVERRIDE_REFUSED')
        self.step(state, tool='foreground_action', expect='INVALID_ARGUMENT')
        after = self.step(state)
        self.assertFalse(after['effect_verified'])
        self.assertNotEqual(after['state_id'], state['state_id'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=1')
        self.step(state, expect='STALE_WORKFLOW_STATE')
        self.step(after, client=self.b, expect='UNKNOWN_WORKFLOW_SESSION')
        self.call(self.a, 'end_window_session', session_id=state['session_id'])
        self.assertTrue(w.U.IsWindow(self.hwnd))
        self.assertFalse(self.a[0].targets)
        self.assertTrue(self.call(self.a, 'end_window_session', session_id=state['session_id'])['already_absent'])

    def test_readonly_and_foreground_upgrade_refused(self):
        self.begin(access='observe_and_foreground', expect='INVALID_ARGUMENT')
        state = self.begin(access='observe')
        after = self.step(state)
        self.assertTrue(after['input_blocked'])
        self.assertEqual(after['action']['attempt_input'], 'not_sent')
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=0')

    def test_stop_and_expiry_never_reacquire(self):
        state = self.begin()
        self.call(self.b, 'input_control', operation='stop')
        with patch.object(w, 'click', wraps=w.click) as native_click:
            after = self.step(state)
        native_click.assert_not_called()
        self.assertTrue(after['input_blocked'])
        self.begin(client=self.b, expect='EXECUTOR_STOPPED')
        self.assertTrue(self.call(self.b, 'input_control', operation='status')['stopped'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=0')
        self.assertEqual(after['action']['attempt_input'], 'not_sent')

    def test_expired_lease_blocks_and_allows_other_owner(self):
        state = self.begin()
        self.now += 61
        after = self.step(state)
        self.assertTrue(after['input_blocked'])
        self.assertEqual(after['action']['attempt_input'], 'not_sent')
        other = self.begin(client=self.b)
        self.assertFalse(other['input_blocked'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=0')

    def test_begin_failure_cleans_own_binding(self):
        original = self.a[0].call
        def fail(name, args):
            if name == 'get_window_state':
                raise w.PilotError('CONTROLLED_OBSERVATION_FAILURE')
            return original(name, args)
        with patch.object(self.a[0], 'call', side_effect=fail):
            self.begin(expect='CONTROLLED_OBSERVATION_FAILURE')
        self.assertFalse(self.a[0].workflow.sessions)
        self.assertFalse(self.a[0].targets)
        self.assertFalse(self.a[0].bindings)
        self.assertFalse(self.begin(client=self.b)['input_blocked'])

    def test_partial_begin_blocks_input(self):
        from window_pilot import uia
        original = uia.observe
        with patch.object(uia, 'observe', side_effect=lambda *a, **kw: original(*a, **kw, timeout=0.001)):
            state = self.begin()
        self.assertEqual(state['state']['status'], 'partial')
        self.assertTrue(state['input_blocked'])
        self.step(state, expect='WORKFLOW_INPUT_BLOCKED')
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=0')

    def test_post_action_observation_failure_preserves_result_and_fault(self):
        state = self.begin()
        original = self.a[0].call
        def fail(name, args):
            if name == 'get_window_state':
                raise w.PilotError('CONTROLLED_POST_ACTION_OBSERVATION_FAILURE')
            return original(name, args)
        with patch.object(self.a[0], 'call', side_effect=fail):
            after = self.step(state)
        self.assertTrue(after['action']['input_sent'])
        self.assertIsNone(after['state'])
        self.assertTrue(after['input_blocked'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=1')
        self.step(after, expect='WORKFLOW_INPUT_BLOCKED')
        target = self.a[0].targets[state['state']['target_id']]
        self.a[0].dispose()
        self.assertTrue(w.U.IsWindow(self.hwnd))
        status = self.coordinator.status('b', target)
        self.assertFalse(status['owned'])
        self.assertTrue(status['faulted'])
        self.assertFalse(self.a[0].workflow.sessions)

    def test_unknown_result_locks_even_with_successful_observation(self):
        state = self.begin()
        original = self.a[0].dispatch
        def unknown(name, args):
            result = original(name, args)
            return {**result, 'status': 'unknown'} if name == 'click' else result
        with patch.object(self.a[0], 'dispatch', side_effect=unknown):
            after = self.step(state)
        self.assertTrue(after['input_blocked'])
        self.assertEqual(after['action']['status'], 'unknown')
        self.assertEqual(after['state']['status'], 'ok')
        self.step(after, expect='WORKFLOW_INPUT_BLOCKED')
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=1')
        self.call(self.a, 'end_window_session', session_id=state['session_id'])
        other = self.begin(client=self.b)
        blocked = self.step(other, client=self.b)
        self.assertTrue(blocked['input_blocked'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=1')

    def test_dispose_releases_without_closing_external_fixture(self):
        state = self.begin()
        self.a[0].dispose()
        self.a[0].dispose()
        self.assertTrue(w.U.IsWindow(self.hwnd))
        self.assertFalse(self.a[0].targets)
        self.assertFalse(self.a[0].frames)
        self.assertFalse(self.a[0].control_observations)
        self.assertFalse(self.a[0].workflow.sessions)
        other = self.begin(client=self.b)
        self.assertFalse(self.step(other, client=self.b)['input_blocked'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=1')

    def test_readonly_end_preserves_other_workflow_lease(self):
        writer = self.begin()
        reader = self.begin(access='observe')
        target = self.a[0].targets[writer['state']['target_id']]
        self.call(self.a, 'end_window_session', session_id=reader['session_id'])
        self.assertTrue(self.coordinator.status('a', target)['owner_is_this_connection'],
                        'ending an observe-only session released the write workflow lease')

    def test_failed_readonly_begin_preserves_existing_writer(self):
        writer = self.begin()
        target = self.a[0].targets[writer['state']['target_id']]
        original = self.a[0].call
        def fail(name, args):
            if name == 'get_window_state':
                raise w.PilotError('CONTROLLED_READONLY_OBSERVATION_FAILURE')
            return original(name, args)
        with patch.object(self.a[0], 'call', side_effect=fail):
            self.begin(access='observe', expect='CONTROLLED_READONLY_OBSERVATION_FAILURE')
        self.assertTrue(self.coordinator.status('a', target)['owner_is_this_connection'],
                        'failed observe-only begin released the existing write workflow lease')

    def test_duplicate_write_begin_refuses_and_original_remains_usable(self):
        writer = self.begin()
        token = writer['state']['target_id']
        self.begin(expect='WORKFLOW_WRITE_TARGET_ALREADY_BOUND')
        self.assertEqual(set(self.a[0].targets), {token})
        self.assertEqual(set(self.a[0].workflow.sessions), {writer['session_id']})
        after = self.step(writer)
        self.assertFalse(after['input_blocked'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=1')

    def test_end_preserves_later_low_level_writer_lease(self):
        writer = self.begin()
        low = self.call(self.a, 'bind_window', hwnd=self.hwnd, access='observe_and_click',
                        purpose='own fixture later low-level binding')['target_id']
        target = self.a[0].targets[low]
        self.call(self.a, 'end_window_session', session_id=writer['session_id'])
        self.assertEqual(set(self.a[0].targets), {low})
        status = self.call(self.a, 'window_control', target_id=low, operation='status')
        self.assertTrue(status['owner_is_this_connection'])
        self.assertTrue(w.U.IsWindow(self.hwnd))
        frame = self.call(self.a, 'observe', target_id=low)
        result = self.call(self.a, 'click', target_id=low, frame_id=frame['frame_id'], x=40, y=40)
        self.assertTrue(result['input_sent'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=1')
        self.assertTrue(self.coordinator.status('a', target)['owner_is_this_connection'])

    def test_independent_connection_competition_and_normal_end_handoff(self):
        writer = self.begin()
        self.begin(client=self.b, expect='WINDOW_OWNED_BY_ANOTHER_CONNECTION')
        self.assertFalse(self.b[0].workflow.sessions)
        self.assertFalse(self.b[0].targets)
        self.assertFalse(self.step(writer)['input_blocked'])
        self.call(self.a, 'end_window_session', session_id=writer['session_id'])
        other = self.begin(client=self.b)
        self.assertFalse(self.step(other, client=self.b)['input_blocked'])
        self.assertEqual(w.text(self.hwnd), 'Window Pilot Test | clicks=2')

    def test_control_value_audit_redaction(self):
        state = self.begin(access='observe_and_control')
        edit = next(node for node in state['state']['accessibility']['nodes'] if node['class_name'] == 'Edit')
        result = w.C.c_size_t()
        self.assertTrue(w.U.SendMessageTimeoutW(edit['native_window_handle'], 0xCF, 0, 0,
                                               0x23, 1000, w.C.byref(result)))
        self.call(self.a, 'end_window_session', session_id=state['session_id'])
        state = self.begin(access='observe_and_control')
        edit = next(node for node in state['state']['accessibility']['nodes'] if node['class_name'] == 'Edit')
        marker = 'workflow-audit-private-marker-123'
        after = self.step(state, tool='control_action', action_args={
            'control_id': edit['control_id'], 'action': 'set_value', 'value': marker})
        self.assertFalse(after['input_blocked'])
        buffer = w.C.create_unicode_buffer(256)
        self.assertTrue(w.U.SendMessageTimeoutW(edit['native_window_handle'], 0xD, 256,
            w.C.addressof(buffer), 0x23, 1000, w.C.byref(result)))
        self.assertEqual(buffer.value, marker)
        audit_files = list((self.root / '.local').rglob('*.jsonl'))
        self.assertTrue(audit_files)
        audit = '\n'.join(path.read_text(encoding='utf8') for path in audit_files)
        self.assertNotIn(marker, audit)
        self.assertIn('value_length', audit)


@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class WindowWorkflowStdioTests(unittest.TestCase):
    def test_real_stdio_three_step_images_single_action_and_cleanup(self):
        if os.environ.get('CI') and os.environ.get('WINDOW_PILOT_NATIVE_TESTS') != '1':
            self.skipTest('interactive own-fixture evidence is opt-in')
        if not w.U.GetForegroundWindow():
            self.skipTest('no interactive desktop')
        root = EVIDENCE / 'stdio'
        root.mkdir(parents=True, exist_ok=True)
        config = root / 'config.json'
        config.write_text('{"window_control":{"capture_backend":"printwindow"}}')
        replies = queue.Queue()
        events = []
        sequence = 0
        hwnd = None
        with (root / 'stderr.txt').open('wb') as errors:
            process = subprocess.Popen([sys.executable, '-I', '-S',
                str(PROJECT / 'scripts/runtime_entry.py'), 'serve', '--config', str(config)],
                cwd=PROJECT, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
            def read():
                for line in process.stdout:
                    replies.put(line)
            reader = threading.Thread(target=read, daemon=True)
            reader.start()
            def rpc(method, params):
                nonlocal sequence
                sequence += 1
                request = {'jsonrpc': '2.0', 'id': sequence, 'method': method, 'params': params}
                process.stdin.write((json.dumps(request) + '\n').encode())
                process.stdin.flush()
                response = json.loads(replies.get(timeout=20))
                self.assertEqual(response['id'], sequence)
                self.assertNotIn('error', response)
                return response['result']
            def call(name, **args):
                response = rpc('tools/call', {'name': name, 'arguments': args})
                self.assertFalse(response['isError'], response)
                metadata = json.loads(response['content'][0]['text'])
                events.append({'tool': name, 'value': metadata})
                images = [part for part in response['content'] if part['type'] == 'image']
                if name in ('begin_window_session', 'act_and_observe'):
                    self.assertEqual(len(images), 1)
                    self.assertEqual(images[0]['mimeType'], 'image/png')
                    data = base64.b64decode(images[0]['data'], validate=True)
                    self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
                    (root / f'{name}.png').write_bytes(data)
                return metadata
            try:
                rpc('initialize', {'protocolVersion': '2025-06-18'})
                tools = rpc('tools/list', {})['tools']
                self.assertEqual(len(tools), 19)
                self.assertTrue({'begin_window_session', 'act_and_observe', 'end_window_session'} <=
                                {tool['name'] for tool in tools})
                launched = call('launch_test')
                hwnd = launched['windows'][0]['hwnd']
                state = call('begin_window_session', hwnd=hwnd, access='observe_and_click',
                             purpose='own stdio workflow fixture', capture_backend='printwindow')
                self.assertEqual(state['state']['status'], 'ok')
                self.assertTrue(state['state']['accessibility']['nodes'])
                after = call('act_and_observe', session_id=state['session_id'], state_id=state['state_id'],
                             tool='click', action_args={'x': 40, 'y': 40})
                self.assertFalse(after['effect_verified'])
                self.assertFalse(after['input_blocked'])
                self.assertTrue(after['action']['input_sent'])
                self.assertEqual(w.text(hwnd), 'Window Pilot Test | clicks=1')
                self.assertNotEqual(state['state']['screenshot']['sha256'],
                                    after['state']['screenshot']['sha256'])
                call('end_window_session', session_id=state['session_id'])
                self.assertTrue(w.U.IsWindow(hwnd))
                call('end_window_session', session_id=state['session_id'])
            finally:
                process.stdin.close()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                reader.join(timeout=2)
                process.stdout.close()
                (root / 'events.json').write_text(json.dumps(events, indent=2), encoding='utf8')
            self.assertEqual(process.returncode, 0)
            self.assertFalse(w.U.IsWindow(hwnd), 'fixture outlived its owning stdio child')


if __name__ == '__main__':
    unittest.main(verbosity=2)
