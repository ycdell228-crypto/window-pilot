"""Private, one-session browser worker transport. No retry or worker restart."""
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import uuid


class BrowserTransportError(RuntimeError):
    pass


class BrowserTransport:
    def __init__(self, *, node, worker, browser, playwright):
        # Paths come from host configuration, not MCP input. Never execute through a shell.
        for path in (node, worker, browser):
            if not Path(path).is_absolute() or not Path(path).is_file():
                raise BrowserTransportError('BROWSER_HOST_PATH_INVALID')
        if not Path(playwright).is_absolute() or not Path(playwright).exists():
            raise BrowserTransportError('BROWSER_PLAYWRIGHT_PATH_INVALID')
        env = {**os.environ, 'WINDOW_PILOT_BROWSER': str(browser), 'WINDOW_PILOT_PLAYWRIGHT': str(playwright)}
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._ended = False
        self._broken = False
        self._replies = queue.Queue(maxsize=2)
        from .browser_job import BrowserJob
        self._job = BrowserJob()
        self._cleanup_done = threading.Event()
        try:
            self.process = subprocess.Popen([str(node), str(worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            # The worker launches Chrome only after a request; assignment precedes every request.
            self._job.assign(self.process.pid)
        except Exception:
            if hasattr(self, 'process'):
                self.process.terminate()
                self.process.wait(timeout=5)
            self._job.close()
            raise
        threading.Thread(target=self._reap, daemon=True).start()
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._reader.start()

    def _reap(self):
        self.process.wait()
        if self._job.finish():
            self._cleanup_done.set()

    def cleanup_complete(self):
        return self._cleanup_done.is_set()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(8 * 1024 * 1024 + 1)
                if not line or len(line) > 8 * 1024 * 1024 or not line.endswith(b'\n'):
                    break
                result = json.loads(line)
                self._replies.put_nowait(result)
        except (ValueError, OSError, queue.Full):
            pass
        finally:
            self.process.stdout.close()
            try:
                self._replies.put_nowait(None)
            except queue.Full:
                pass

    def request(self, operation, args=None, *, timeout=25, check_running=None):
        if not self._lock.acquire(blocking=False):
            raise BrowserTransportError('BROWSER_TRANSPORT_BUSY')
        sent = False
        try:
            if self._ended or self._broken:
                raise BrowserTransportError('BROWSER_TRANSPORT_CLOSED')
            if operation not in {'begin', 'observe', 'step', 'end', 'status'}:
                raise BrowserTransportError('BROWSER_INVALID_OPERATION')
            if check_running:
                check_running()
            request_id = uuid.uuid4().hex
            payload = json.dumps({'id': request_id, 'operation': operation, 'args': args or {}}, ensure_ascii=True).encode() + b'\n'
            if len(payload) > 65536:
                raise BrowserTransportError('BROWSER_REQUEST_TOO_LARGE')
            with self._write_lock:
                if self._ended:
                    raise BrowserTransportError('BROWSER_TRANSPORT_CLOSED')
                sent = True  # A failed write can still have delivered a prefix; never replay.
                self.process.stdin.write(payload)
                self.process.stdin.flush()
            import time
            deadline = time.monotonic() + timeout
            while True:
                if check_running:
                    check_running()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                try:
                    reply = self._replies.get(timeout=min(remaining, 0.05))
                    break
                except queue.Empty:
                    continue
            if not isinstance(reply, dict) or reply.get('id') != request_id or type(reply.get('ok')) is not bool:
                raise ValueError('invalid reply')
            return reply
        except Exception as error:
            if sent:
                self._broken = True
                self.close(wait=False)
                raise BrowserTransportError('BROWSER_COMMUNICATION_UNKNOWN: request may have executed; no replay') from error
            raise
        finally:
            self._lock.release()

    def close(self, *, wait=True):
        # May run concurrently with a request: EOF asks the worker to cancel and close its browser.
        with self._write_lock:
            self._ended = True
            if not self.process.stdin.closed:
                try:
                    self.process.stdin.close()
                except OSError:
                    pass
        if wait:
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                pass
            if self.process.poll() is not None:
                self._cleanup_done.wait(timeout=3.1)
        return {'worker_exited': self.process.poll() is not None,
                'cleanup': 'worker_exited' if self.cleanup_complete() else 'pending_unverified'}

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
