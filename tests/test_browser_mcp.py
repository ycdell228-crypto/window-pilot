"""Real headless local-site acceptance; no desktop input or installed executor."""
import base64
import json
import os
import sys
from pathlib import Path
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
if sys.platform == 'win32':
    from window_pilot.service import Service
    from window_pilot.rpc import Dispatcher
    from window_pilot.coordination import Coordinator
    from window_pilot.browser_transport import BrowserTransportError

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / '.local/browser-mcp-test'
NODE = os.environ.get('WINDOW_PILOT_TEST_NODE', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'))
PLAYWRIGHT = os.environ.get('WINDOW_PILOT_TEST_PLAYWRIGHT', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright'))
CHROME = os.environ.get('WINDOW_PILOT_TEST_CHROME', 'C:/Program Files/Google/Chrome/Application/chrome.exe')

@unittest.skipUnless(sys.platform == 'win32', 'Windows only')
class BrowserMCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get('WINDOW_PILOT_BROWSER_TESTS') != '1':
            raise unittest.SkipTest('real local Chrome acceptance is opt-in')
        if not all(Path(p).exists() for p in (NODE, PLAYWRIGHT, CHROME)):
            raise unittest.SkipTest('configured browser acceptance dependencies unavailable')
    def setUp(self):
        self.root = EVIDENCE / self._testMethodName
        self.root.mkdir(parents=True, exist_ok=True)
        self.posts = []
        self.slow_post = False
        self.arrived = threading.Event()
        self.release = threading.Event()
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                body = b'''<!doctype html><title>Browser MCP acceptance</title><h1>Own local form</h1><form method="post" action="/submit"><label>Name<input name="name"></label><button>Submit once</button></form><button onclick="fetch('/slow')">Slow</button>'''
                if self.path == '/slow':
                    owner.arrived.set()
                    owner.release.wait(8)
                self.send_response(200); self.end_headers()
                try: self.wfile.write(body)
                except OSError: pass
            def do_POST(self):
                owner.posts.append(self.rfile.read(int(self.headers['Content-Length'])).decode())
                if owner.slow_post:
                    owner.arrived.set(); owner.release.wait(8)
                self.send_response(200); self.end_headers()
                try: self.wfile.write(b'<h1>Submitted exactly once</h1>')
                except OSError: pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.cfg = self.root / 'config.json'
        self.cfg.write_text(json.dumps({'browser': {'enabled': True, 'node': NODE, 'executable': CHROME, 'playwright': PLAYWRIGHT, 'allowed_origins': [self.origin]}}))
        self.coordinator = Coordinator()
        self.services = []
        self.workers = []
        self.events = []
        self.seq = 0
        self.a = self.connect('a'); self.b = self.connect('b')
    def connect(self, name):
        s = Service(self.cfg, self.root / (name + '.lock'), coordinator=self.coordinator, connection_id=name)
        self.services.append(s)
        return s, Dispatcher(s)
    def tearDown(self):
        self.release.set()
        workers = self.workers
        for s in self.services: s.dispose()
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)
        self.events.append({'cleanup': [{'pid': t.process.pid, 'exit': t.process.poll(), 'cleanup_complete': t.cleanup_complete()} for t in workers], 'posts': self.posts})
        (self.root / 'events.json').write_text(json.dumps(self.events, indent=2), encoding='utf8')
        self.assertTrue(all(t.process.poll() is not None and t.cleanup_complete() for t in workers))
        self.assertFalse(self.thread.is_alive())
    def call(self, client=None, expect=None, tool='browser_session', **args):
        self.seq += 1
        r = (client or self.a)[1].handle({'jsonrpc': '2.0', 'id': self.seq, 'method': 'tools/call', 'params': {'name': tool, 'arguments': args}})['result']
        txt = r['content'][0]['text']
        self.events.append({'args': {k:v for k,v in args.items() if k != 'value'}, 'error': r['isError'], 'text': txt})
        if expect:
            self.assertTrue(r['isError'], txt); self.assertIn(expect, txt)
            if expect in ('APPLICATION_ACCESS_NOT_GRANTED', 'ACCESS_POLICY_UNAVAILABLE_OR_INVALID'):
                self.assertEqual(json.loads(r['content'][1]['text'])['recovery_diagnostic']['attempt_input'], 'not_sent')
            return txt
        self.assertFalse(r['isError'], txt)
        val = json.loads(txt)
        for c in r['content'][1:]:
            if c['type'] == 'image':
                raw = base64.b64decode(c['data'], validate=True); self.assertEqual(raw[:8], b'\x89PNG\r\n\x1a\n')
                (self.root / f'{self.seq}.png').write_bytes(raw)
        return val
    def begin(self, client=None):
        client = client or self.a
        state = self.call(client, operation='begin', url=self.origin, purpose='own isolated acceptance')
        self.workers.append(client[0].browser.sessions[state['session_id']])
        return state
    def step(self, state, label, **args):
        node = next(n for n in state['result']['state']['nodes'] if n['name'] == label)
        return self.call(operation='step', session_id=state['session_id'], control_id=node['control_id'], **args)
    def test_real_form_single_submit_images_and_ownership(self):
        state = self.begin(); self.assertTrue(state['ok']); self.assertFalse(state['effect_verified'])
        sid = state['session_id']
        for operation in ('status', 'observe', 'end'):
            self.call(self.b, operation=operation, session_id=sid, expect='UNKNOWN_BROWSER_SESSION')
        state = self.step(state, 'Name', action='set_value', value='MCP acceptance')
        state = self.step(state, 'Submit once', action='click')
        self.assertEqual(self.posts, ['name=MCP+acceptance'])
        self.assertIn('Submitted exactly once', state['result']['state']['document_text'])
        self.assertTrue(self.call(operation='end', session_id=sid)['worker_exited'])
    def test_default_disabled_and_exact_origin(self):
        self.a[0].config = {}
        self.call(operation='begin', url=self.origin, purpose='test', expect='BROWSER_DISABLED_BY_OPERATOR')
        self.a[0].config = json.loads(self.cfg.read_text())
        for url in ('http://localhost:1', 'https://127.0.0.1:1', self.origin+'0', 'http://user@127.0.0.1:1'):
            self.call(operation='begin', url=url, purpose='test', expect='BROWSER_ORIGIN_NOT_AUTHORIZED')
        self.assertFalse(self.a[0].browser.sessions)
    def test_stop_cross_connection_idle_resume_no_restart_disconnect(self):
        a = self.begin(); b = self.begin(self.b)
        stop = self.coordinator.stop_input()
        for s in self.services:
            for t in s.browser.sessions.values(): t.close(); self.assertTrue(t.cleanup_complete())
        resumed = self.coordinator.resume_input(stop['stop_id']); self.assertFalse(resumed['stopped'])
        self.call(operation='observe', session_id=a['session_id'], expect='BROWSER_TRANSPORT_CLOSED')
        fresh = self.begin(); t = self.a[0].browser.sessions[fresh['session_id']]
        self.a[0].dispose(); self.assertIsNotNone(t.process.poll())
    def test_unknown_step_origin_cannot_be_bypassed(self):
        state = self.begin(); t = self.a[0].browser.sessions[state['session_id']]
        with patch.object(t, 'request', side_effect=BrowserTransportError('BROWSER_COMMUNICATION_UNKNOWN controlled')):
            self.call(operation='step', session_id=state['session_id'], control_id='x', action='click', expect='BROWSER_COMMUNICATION_UNKNOWN')
        self.begin_error = self.call(self.b, operation='begin', url=self.origin, purpose='test', expect='BROWSER_ORIGIN_INPUT_UNKNOWN')
        stop = self.coordinator.stop_input(); t.close(); self.assertTrue(t.cleanup_complete()); self.coordinator.resume_input(stop['stop_id'])
        self.call(self.b, operation='begin', url=self.origin, purpose='test', expect='BROWSER_ORIGIN_INPUT_UNKNOWN')
    def test_foreground_gate_no_actual_desktop_input(self):
        self.coordinator._foreground = True
        self.call(operation='begin', url=self.origin, purpose='test', expect='FOREGROUND_INPUT_IN_FLIGHT')
        self.assertFalse(self.a[0].browser.sessions)

    def test_stop_in_flight_submit_no_replay(self):
        state = self.begin(); self.slow_post = True
        node = next(n for n in state['result']['state']['nodes'] if n['name'] == 'Submit once')
        replies = []
        thread = threading.Thread(target=lambda: replies.append(self.call(operation='step', session_id=state['session_id'], control_id=node['control_id'], action='click', expect='BROWSER_COMMUNICATION_UNKNOWN')))
        thread.start(); self.assertTrue(self.arrived.wait(5))
        stop = self.coordinator.stop_input()
        thread.join(10); self.assertFalse(thread.is_alive()); self.assertEqual(len(replies), 1)
        self.release.set()
        for t in self.a[0].browser.sessions.values(): t.close(); self.assertTrue(t.cleanup_complete())
        self.coordinator.resume_input(stop['stop_id'])
        self.assertEqual(self.posts, ['name='])
        self.call(self.b, operation='begin', url=self.origin, purpose='test', expect='BROWSER_ORIGIN_INPUT_UNKNOWN')

    def test_origin_gate_rechecked_at_command_admission(self):
        original = self.coordinator.require_browser_origin
        checks = []
        def fault_after_first_check(origin):
            original(origin); checks.append(origin)
            if len(checks) == 1: self.coordinator.fault_browser_origin(origin)
        with patch.object(self.coordinator, 'require_browser_origin', side_effect=fault_after_first_check):
            self.call(operation='begin', url=self.origin, purpose='test', expect='BROWSER_ORIGIN_INPUT_UNKNOWN')
        self.assertFalse(self.a[0].browser.sessions)

    def test_same_origin_commands_cannot_overlap(self):
        with self.coordinator.browser_command(self.origin):
            self.call(self.b, operation='begin', url=self.origin, purpose='test', expect='BROWSER_ORIGIN_OPERATION_IN_FLIGHT')
        self.assertFalse(self.b[0].browser.sessions)

    def test_ended_sessions_do_not_consume_capacity(self):
        for _ in range(9):
            state = self.begin()
            self.assertTrue(self.call(operation='end', session_id=state['session_id'])['worker_exited'])

    def grant(self, **updates):
        cfg = json.loads(self.cfg.read_text())
        grant = {'id': 'own-test', 'expires_at': (datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),
                 'access': ['browser'], 'origins': [self.origin]}
        grant.update(updates)
        cfg['authorization'] = {'mode': 'enforced', 'grants': [grant]}
        self.cfg.write_text(json.dumps(cfg))

    def test_enforced_real_action_then_revoke_cleanup(self):
        self.grant(); state = self.begin()
        state = self.step(state, 'Name', action='set_value', value='operator granted')
        self.assertEqual(next(n['value'] for n in state['result']['state']['nodes'] if n['name']=='Name'), 'operator granted')
        self.grant(revoked=True)
        self.call(operation='step', session_id=state['session_id'], control_id='unused', action='set_value', value='PRIVATE_UNSENT', expect='APPLICATION_ACCESS_NOT_GRANTED')
        self.assertTrue(self.call(operation='end', session_id=state['session_id'])['worker_exited'])
        self.assertNotIn('PRIVATE_UNSENT', json.dumps(self.events))

    def test_revocation_during_dispatched_submit_is_unknown(self):
        self.grant(); state = self.begin(); self.slow_post=True
        node = next(n for n in state['result']['state']['nodes'] if n['name']=='Submit once')
        replies=[]
        thread=threading.Thread(target=lambda: replies.append(self.call(operation='step', session_id=state['session_id'], control_id=node['control_id'], action='click', expect='BROWSER_COMMUNICATION_UNKNOWN')))
        thread.start(); self.assertTrue(self.arrived.wait(5)); self.grant(revoked=True)
        thread.join(10); self.release.set(); self.assertFalse(thread.is_alive()); self.assertEqual(len(replies),1)
        self.assertEqual(self.posts,['name='])
        self.assertTrue(self.call(operation='end',session_id=state['session_id'])['worker_exited'])
        self.grant()
        self.call(self.b,operation='begin',url=self.origin,purpose='test',expect='BROWSER_ORIGIN_INPUT_UNKNOWN')

if __name__ == '__main__': unittest.main()
