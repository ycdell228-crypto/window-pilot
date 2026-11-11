"""Owned headless browser crash acceptance; never selects existing browsers."""
import base64
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.local/browser-crash-test'
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / 'src'))
CONFIG = dict(node=os.environ.get('WINDOW_PILOT_TEST_NODE', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')),
    worker=str(ROOT / 'scripts/browser-worker.mjs'), browser=os.environ.get('WINDOW_PILOT_TEST_CHROME', 'C:/Program Files/Google/Chrome/Application/chrome.exe'),
    playwright=os.environ.get('WINDOW_PILOT_TEST_PLAYWRIGHT', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')))


def child(url, name):
    from window_pilot.browser_transport import BrowserTransport
    t = BrowserTransport(**CONFIG)
    print(json.dumps({'node': t.process.pid}), flush=True)
    def begin():
        try:
            reply = t.request('begin', {'url': url, 'purpose': 'owned crash cleanup acceptance'})
            assert reply['ok'], reply
            result = reply['result']
            (OUT / (name + '.png')).write_bytes(base64.b64decode(result['state']['image']))
            print(json.dumps({'chrome': result['session']['pid'], 'begun': True}), flush=True)
        except Exception as e:
            print(json.dumps({'begin_error': str(e)}), flush=True)
    task = threading.Thread(target=begin)
    task.start()
    command = sys.stdin.readline().strip()
    if command == 'eof':
        result = t.close()
    elif command == 'await_reaper':
        until = time.monotonic() + 10
        while not t.cleanup_complete() and time.monotonic() < until:
            time.sleep(.02)
        result = {'cleanup_complete': t.cleanup_complete()}
    else:
        result = t.close()
    task.join(20)
    print(json.dumps({'cleanup': result, 'begin_thread_exited': not task.is_alive()}), flush=True)


class Entry(C.Structure):
    _fields_ = [('size', W.DWORD), ('usage', W.DWORD), ('pid', W.DWORD), ('heap', C.c_size_t),
        ('module', W.DWORD), ('threads', W.DWORD), ('parent', W.DWORD), ('priority', W.LONG),
        ('flags', W.DWORD), ('exe', W.WCHAR * 260)]


K = C.WinDLL('kernel32', use_last_error=True)
for name, args, restype in [
    ('CreateToolhelp32Snapshot', [W.DWORD, W.DWORD], W.HANDLE),
    ('Process32FirstW', [W.HANDLE, C.POINTER(Entry)], W.BOOL),
    ('Process32NextW', [W.HANDLE, C.POINTER(Entry)], W.BOOL),
    ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
    ('GetProcessTimes', [W.HANDLE] + [C.POINTER(W.FILETIME)] * 4, W.BOOL),
    ('WaitForSingleObject', [W.HANDLE, W.DWORD], W.DWORD),
    ('TerminateProcess', [W.HANDLE, W.UINT], W.BOOL),
    ('CloseHandle', [W.HANDLE], W.BOOL),
]:
    fn = getattr(K, name); fn.argtypes = args; fn.restype = restype


def capture(root, tracked):
    snap = K.CreateToolhelp32Snapshot(2, 0)
    assert snap != C.c_void_p(-1).value
    rows = []
    e = Entry(); e.size = C.sizeof(e)
    try:
        ok = K.Process32FirstW(snap, C.byref(e))
        while ok:
            rows.append((e.pid, e.parent, e.exe))
            ok = K.Process32NextW(snap, C.byref(e))
    finally:
        K.CloseHandle(snap)
    owned = {root} | set(tracked)
    while True:
        new = {pid for pid, parent, exe in rows if parent in owned}
        if new <= owned: break
        owned |= new
    for pid, parent, exe in rows:
        if pid not in owned or pid in tracked: continue
        h = K.OpenProcess(0x100000 | 0x1000 | 1, False, pid)
        if not h: continue  # A process may exit between snapshot and OpenProcess.
        times = [W.FILETIME() for _ in range(4)]
        assert K.GetProcessTimes(h, *[C.byref(x) for x in times])
        tracked[pid] = {'handle': h, 'pid': pid, 'parent': parent, 'exe': exe,
                        'creation_filetime': times[0].dwHighDateTime << 32 | times[0].dwLowDateTime}


def supervisor():
    beats = []
    class Page(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def handle(self):
            try: super().handle()
            except (ConnectionResetError, ConnectionAbortedError): pass
        def do_GET(self):
            if self.path.startswith('/beat'): beats.append(time.monotonic())
            body = b'<title>Owned crash test</title><h1>Owned headless crash cleanup</h1><label>Name<input value="crash-test"></label><script>setInterval(()=>fetch("/beat"),100)</script>'
            self.send_response(200); self.end_headers()
            try: self.wfile.write(body)
            except OSError: pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Page)
    thread = threading.Thread(target=server.serve_forever); thread.start()
    records = []
    try:
        for name in ['normal_eof', 'kill_node', 'kill_parent', 'early_eof', 'launch_eof']:
            proc = subprocess.Popen([sys.executable, __file__, '--child', f'http://127.0.0.1:{server.server_port}/', name],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            tracked = {}; lines = []
            def read():
                for line in proc.stdout: lines.append(json.loads(line))
            reader = threading.Thread(target=read); reader.start()
            try:
                deadline = time.monotonic() + 30
                while not any('node' in x for x in lines) and time.monotonic() < deadline:
                    capture(proc.pid, tracked); time.sleep(.01)
                assert any('node' in x for x in lines), lines
                node = next(x['node'] for x in lines if 'node' in x)
                if name == 'early_eof':
                    # Cancel during Chrome startup rather than waiting for begin observation.
                    for _ in range(8): capture(proc.pid, tracked); time.sleep(.01)
                elif name == 'launch_eof':
                    # Observe an actual Chrome process but cancel before begin can finish.
                    while not any(r['exe'].lower() == 'chrome.exe' for r in tracked.values()) and time.monotonic() < deadline:
                        capture(proc.pid, tracked); time.sleep(.005)
                    assert any(r['exe'].lower() == 'chrome.exe' for r in tracked.values())
                    assert not any(x.get('begun') for x in lines), lines
                else:
                    while not any(x.get('begun') for x in lines) and time.monotonic() < deadline:
                        capture(proc.pid, tracked); time.sleep(.02)
                    assert any(x.get('begun') for x in lines), lines
                    time.sleep(.3)
                capture(proc.pid, tracked)
                assert node in tracked
                if name == 'kill_parent':
                    assert K.TerminateProcess(tracked[proc.pid]['handle'], 88)
                else:
                    if name == 'kill_node': assert K.TerminateProcess(tracked[node]['handle'], 89)
                    proc.stdin.write('await_reaper\n' if name == 'kill_node' else 'eof\n'); proc.stdin.flush()
                proc.wait(timeout=25); reader.join(3)
                exited = {str(pid): K.WaitForSingleObject(row['handle'], 5000) == 0 for pid, row in tracked.items()}
                assert all(exited.values()), exited
                if name != 'kill_parent':
                    clean = next(x['cleanup'] for x in lines if 'cleanup' in x)
                    assert clean.get('cleanup_complete') is True or clean.get('cleanup') == 'worker_exited', clean
                count = len(beats); time.sleep(.4)
                assert count == len(beats), 'heartbeat continued after tree exit'
                rows = [{k: v for k, v in row.items() if k != 'handle'} for row in tracked.values()]
                assert name == 'early_eof' or any(r['exe'].lower() == 'chrome.exe' for r in rows)
                records.append({'case': name, 'status': 'passed', 'processes': rows, 'all_captured_handles_signaled': exited,
                    'child_output': lines, 'heartbeat_stopped': True, 'exitcode': proc.returncode, 'stderr': proc.stderr.read()})
            finally:
                # Only exact handles captured from this newly-created owned tree are eligible.
                for row in tracked.values():
                    if K.WaitForSingleObject(row['handle'], 0) != 0: K.TerminateProcess(row['handle'], 90)
                    K.CloseHandle(row['handle'])
                if proc.poll() is None: proc.terminate(); proc.wait(timeout=5)
                reader.join(3)
    finally:
        server.shutdown(); server.server_close(); thread.join(3)
        records.append({'http_server_thread_exited': not thread.is_alive()})
        (OUT / 'results.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    print(json.dumps({'status': 'passed', 'cases': len(records)-1, 'evidence': str(OUT)}))


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--child': child(sys.argv[2], sys.argv[3])
    else: supervisor()
