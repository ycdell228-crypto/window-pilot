"""Independent real-Chrome acceptance for the private JSON-lines transport."""
import base64
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from window_pilot.browser_transport import BrowserTransport, BrowserTransportError

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / '.local/browser-transport-test'
EVIDENCE.mkdir(parents=True, exist_ok=True)
CONFIG = dict(node=shutil.which('node'), worker=str(ROOT / 'scripts/browser-worker.mjs'),
              browser=os.environ['WINDOW_PILOT_BROWSER'], playwright=os.environ['WINDOW_PILOT_PLAYWRIGHT'])
records = []
transports = []
submissions = []
slow_started = threading.Event()
release_slow = threading.Event()


class Page(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/slow':
            slow_started.set()
            release_slow.wait(8)
        body = b'''<label>Name<input value="original"></label><button onclick="fetch('/save',{method:'POST',body:document.querySelector('input').value}).then(r=>r.text()).then(t=>document.querySelector('output').textContent=t)">Save</button><button onclick="location.href='/slow'">Slow</button><output>not saved</output>'''
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_POST(self):
        value = self.rfile.read(int(self.headers['Content-Length'])).decode()
        submissions.append(value)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(('saved:' + value).encode())


def make(**overrides):
    transport = BrowserTransport(**(CONFIG | overrides))
    transports.append(transport)
    return transport


def result(transport, operation, args=None, **kwargs):
    reply = transport.request(operation, args, **kwargs)
    assert reply['ok'], reply
    return reply['result']


def rejects(call, text):
    try:
        call()
    except BrowserTransportError as error:
        assert text in str(error), str(error)
        return str(error)
    raise AssertionError('Expected rejection: ' + text)


def control(state, name):
    return next(n['control_id'] for n in state['nodes'] if n['name'] == name)


def owned_handles(transport, chrome_pid):
    # Capture handles before exit to avoid PID reuse and verify the entire observed tree.
    from ctypes import wintypes
    class ProcessEntry(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('usage', wintypes.DWORD),
                    ('pid', wintypes.DWORD), ('heap', ctypes.c_size_t),
                    ('module', wintypes.DWORD), ('threads', wintypes.DWORD),
                    ('parent', wintypes.DWORD), ('priority', wintypes.LONG),
                    ('flags', wintypes.DWORD), ('exe', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
    kernel.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    assert snapshot != ctypes.c_void_p(-1).value
    processes = []
    entry = ProcessEntry()
    entry.size = ctypes.sizeof(entry)
    try:
        present = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while present:
            processes.append({'ProcessId': entry.pid, 'ParentProcessId': entry.parent})
            present = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    owned = {transport.process.pid, chrome_pid}
    while True:
        descendants = {p['ProcessId'] for p in processes if p['ParentProcessId'] in owned}
        if descendants <= owned:
            break
        owned |= descendants
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handles = [(pid, kernel.OpenProcess(0x00100000, False, pid)) for pid in owned]
    assert all(handle for _, handle in handles), handles
    return kernel, handles


def verify_exit(transport, captured):
    cleanup = transport.close()
    assert cleanup['worker_exited'], cleanup
    kernel, handles = captured
    try:
        exited = {pid: kernel.WaitForSingleObject(handle, 5000) == 0 for pid, handle in handles}
        assert all(exited.values()), exited
        records.append({'cleanup': cleanup, 'owned_process_tree_exited': exited})
    finally:
        for _, handle in handles:
            kernel.CloseHandle(handle)


server = ThreadingHTTPServer(('127.0.0.1', 0), Page)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
start = {'url': f'http://127.0.0.1:{server.server_port}/', 'purpose': 'owned private transport acceptance'}
try:
    transport = make()
    opened = result(transport, 'begin', start)
    captured = owned_handles(transport, opened['session']['pid'])
    state = opened['state']
    response = result(transport, 'step', {'control_id': control(state, 'Name'), 'action': 'set_value', 'value': 'transport-once'})
    assert response['effect_verified'] is False
    response = result(transport, 'step', {'control_id': control(response['state'], 'Save'), 'action': 'click'})
    deadline = time.monotonic() + 3
    while 'saved:transport-once' not in response['state']['document_text'] and time.monotonic() < deadline:
        response = result(transport, 'observe')
    assert submissions == ['transport-once'], submissions
    assert 'saved:transport-once' in response['state']['document_text']
    (EVIDENCE / 'saved.png').write_bytes(base64.b64decode(response['state']['image']))
    records.append({'single_submission': submissions.copy(), 'effect_verified': response['effect_verified']})
    response = result(transport, 'step', {'control_id': control(response['state'], 'Slow'), 'action': 'click'})
    assert response['action']['status'] == 'unknown'
    assert response['input_blocked'] is True
    refused = transport.request('step', {'control_id': 'old', 'action': 'click'})
    assert refused['error'] == 'BROWSER_SESSION_INPUT_BLOCKED', refused
    records.append({'unknown_no_replay': refused})
    ended = result(transport, 'end')
    assert ended['owned_process_exited'] is True
    assert transport.request('observe')['error'] == 'BROWSER_SESSION_ENDED'
    records.append({'explicit_end_refuses_observe': True})
    verify_exit(transport, captured)

    # Cancel a real navigation while request() is polling. A concurrent request must refuse.
    slow_started.clear()
    transport = make()
    opened = result(transport, 'begin', start)
    captured = owned_handles(transport, opened['session']['pid'])
    cancelled = threading.Event()
    errors = []
    def check_running():
        if cancelled.is_set():
            raise RuntimeError('caller cancellation')
    def pending():
        try:
            transport.request('step', {'control_id': control(opened['state'], 'Slow'), 'action': 'click'}, check_running=check_running)
        except BrowserTransportError as error:
            errors.append(str(error))
    task = threading.Thread(target=pending)
    task.start()
    assert slow_started.wait(3)
    rejects(lambda: transport.request('observe'), 'BUSY')
    cancelled.set()
    task.join(3)
    assert not task.is_alive()
    assert errors and 'COMMUNICATION_UNKNOWN' in errors[0], errors
    rejects(lambda: transport.request('step', {}), 'CLOSED')
    records.append({'in_flight_cancel': errors, 'concurrent_request_rejected': True})
    verify_exit(transport, captured)

    # A transport deadline is also terminal and cannot resend the uncertain command.
    slow_started.clear()
    transport = make()
    opened = result(transport, 'begin', start)
    captured = owned_handles(transport, opened['session']['pid'])
    rejects(lambda: transport.request('step', {'control_id': control(opened['state'], 'Slow'), 'action': 'click'}, timeout=0.02), 'COMMUNICATION_UNKNOWN')
    rejects(lambda: transport.request('observe'), 'CLOSED')
    records.append({'timeout_terminal_no_replay': True})
    verify_exit(transport, captured)

    transport = make()
    opened = result(transport, 'begin', start)
    captured = owned_handles(transport, opened['session']['pid'])
    oversized = rejects(lambda: transport.request('step', {'value': 'PRIVATE_SENTINEL' * 6000}), 'TOO_LARGE')
    assert 'PRIVATE_SENTINEL' not in oversized
    assert result(transport, 'status')['opened']
    records.append({'oversized_request_rejected_without_text': oversized})
    verify_exit(transport, captured)

    # Exercise malformed requests directly against the worker, without a browser.
    env = dict(os.environ, WINDOW_PILOT_BROWSER=CONFIG['browser'], WINDOW_PILOT_PLAYWRIGHT=CONFIG['playwright'])
    raw = subprocess.Popen([CONFIG['node'], CONFIG['worker']], stdin=subprocess.PIPE,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        raw.stdin.write(b'{"PRIVATE_SENTINEL":\n')
        raw.stdin.flush()
        invalid = raw.stdout.readline()
        assert b'PRIVATE_SENTINEL' not in invalid
        assert json.loads(invalid)['error'] == 'BROWSER_WORKER_OPERATION_FAILED'
        raw.stdin.write(json.dumps({'id': 'protocol', 'operation': 'begin', 'args':
            {'url': 'https://PRIVATE_SENTINEL.invalid/', 'purpose': 'private'}}).encode() + b'\n')
        raw.stdin.flush()
        refused = raw.stdout.readline()
        assert b'PRIVATE_SENTINEL' not in refused
        assert json.loads(refused)['error'] == 'BROWSER_LOCAL_ORIGIN_REQUIRED'
        raw.stdin.write(b'x' * 65537 + b'\n')
        raw.stdin.flush()
        raw.wait(timeout=5)
        assert b'PRIVATE_SENTINEL' not in raw.stderr.read()
        records.append({'malformed_and_external_protocol_sanitized': True, 'oversized_worker_input_exited': True})
    finally:
        if raw.poll() is None:
            raw.stdin.close()
            raw.wait(timeout=5)

    # An excessive response is terminal even if its prefix resembles valid output.
    fake = EVIDENCE / 'oversized-response.mjs'
    fake.write_text("process.stdin.once('data',()=>process.stdout.write('x'.repeat(8*1024*1024+1)));process.stdin.on('end',()=>process.exit());")
    transport = make(worker=str(fake))
    rejects(lambda: transport.request('status'), 'COMMUNICATION_UNKNOWN')
    rejects(lambda: transport.request('status'), 'CLOSED')
    assert transport.close()['worker_exited']
    records.append({'oversized_response_terminal': True})

    # An unresponsive owned worker must remain explicitly unverified after the deadline.
    fake = EVIDENCE / 'unresponsive-worker.mjs'
    fake.write_text("process.stdin.resume();process.stdin.on('end',()=>{});setInterval(()=>{},1000);")
    transport = make(worker=str(fake))
    before = time.monotonic()
    pending_cleanup = transport.close()
    elapsed = time.monotonic() - before
    assert pending_cleanup == {'worker_exited': False, 'cleanup': 'pending_unverified'}, pending_cleanup
    assert 14 <= elapsed < 20, elapsed
    transport.process.terminate()
    transport.process.wait(timeout=5)
    records.append({'close_deadline_seconds': elapsed, 'deadline_result': pending_cleanup, 'test_worker_terminated': True})

    transport = make(playwright=str(EVIDENCE))
    dependency_error = rejects(lambda: transport.request('status'), 'COMMUNICATION_UNKNOWN')
    assert 'PRIVATE_SENTINEL' not in dependency_error
    assert transport.close()['worker_exited']
    records.append({'dependency_failure_sanitized': dependency_error})
finally:
    release_slow.set()
    for transport in transports:
        transport.close()
    server.shutdown()
    server.server_close()
    thread.join(3)
    records.append({'all_workers_exited': all(t.process.poll() is not None for t in transports), 'http_server_thread_exited': not thread.is_alive()})
    (EVIDENCE / 'results.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
print(json.dumps({'status': 'passed', 'evidence': str(EVIDENCE), 'checks': records}))
