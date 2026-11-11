"""Connection-owned MCP browser sessions; host configuration is separate from task purpose."""
import secrets
import threading
from collections import deque
from urllib.parse import urlsplit
from .browser_transport import BrowserTransport, BrowserTransportError
from .resources import runtime_script
from .win32 import PilotError


class BrowserService:
    def __init__(self, service):
        self.service = service
        self.sessions = {}
        self.retired = deque(maxlen=128)
        self.lock = threading.Lock()

    def call(self, args):
        if not self.lock.acquire(blocking=False):
            raise PilotError('BROWSER_CONNECTION_BUSY')
        try:
            return self._call(args)
        finally:
            self.lock.release()

    def _call(self, args):
        op = args['operation']
        allowed = {'begin': {'url', 'purpose'}, 'step': {'session_id', 'control_id', 'action', 'value'},
                   'observe': {'session_id'}, 'end': {'session_id'}, 'status': {'session_id'}}
        if set(args) - {'operation'} - allowed[op]:
            raise PilotError('BROWSER_UNEXPECTED_ARGUMENTS')
        s = self.service
        if op == 'begin':
            cfg = s.config.get('browser', {})
            if cfg.get('enabled') is not True:
                raise PilotError('BROWSER_DISABLED_BY_OPERATOR')
            url, purpose = args.get('url'), args.get('purpose')
            if not isinstance(url, str) or not isinstance(purpose, str) or not 1 <= len(purpose.strip()) <= 300:
                raise PilotError('BROWSER_URL_AND_PURPOSE_REQUIRED')
            try:
                parsed = urlsplit(url)
                origin = f'http://127.0.0.1:{parsed.port}'
                valid = (parsed.scheme == 'http' and parsed.hostname == '127.0.0.1' and parsed.port
                         and not parsed.username and not parsed.password and origin in cfg.get('allowed_origins', []))
            except ValueError:
                valid = False
            if not valid:
                raise PilotError('BROWSER_ORIGIN_NOT_AUTHORIZED_BY_OPERATOR')
            self.check_before_request(origin)
            s.coordinator.require_browser_origin(origin)
            for old_id, old in list(self.sessions.items()):
                if old.cleanup_complete():
                    self.sessions.pop(old_id)
                    self.retired.append(old_id)
            if len(self.sessions) >= 8:
                raise PilotError('BROWSER_CONNECTION_CAPACITY')
            with s.coordinator.browser_command(origin):
                transport = BrowserTransport(node=cfg.get('node', ''), browser=cfg.get('executable', ''),
                    playwright=cfg.get('playwright', ''), worker=runtime_script('browser-worker.mjs'))
                sid = secrets.token_hex(16)
                self.sessions[sid] = transport
                transport.host_origin = origin
                try:
                    s.coordinator.register_browser((s.connection_id, sid),
                        lambda: transport.close(wait=False), transport.cleanup_complete)
                    reply = transport.request('begin', {'url': url, 'purpose': purpose},
                        check_running=lambda: self.check_policy(origin))
                    if not reply['ok']:
                        transport.close()
                    return self._result(sid, reply)
                except Exception:
                    transport.close()
                    raise
        sid = args.get('session_id')
        if isinstance(sid, str) and sid in self.retired and op in {'end', 'status'}:
            return {'session_id': sid, 'worker_exited': True, 'cleanup': 'worker_exited',
                    'process_tree_cleanup_confirmed': True, 'already_ended': True, 'effect_verified': False}
        if not isinstance(sid, str) or sid not in self.sessions:
            raise PilotError('UNKNOWN_BROWSER_SESSION: connection-scoped session required')
        transport = self.sessions[sid]
        if op == 'end':
            result = transport.close()
            if transport.cleanup_complete():
                self.sessions.pop(sid)
                self.retired.append(sid)
            return {'session_id': sid, **result, 'effect_verified': False}
        if op == 'status':
            return {'session_id': sid, 'worker_exited': transport.process.poll() is not None,
                    'process_tree_cleanup_confirmed': transport.cleanup_complete(),
                    'executor_stop': s.coordinator.stop_status(), 'effect_verified': False}
        if op == 'step':
            s.coordinator.require_browser_origin(transport.host_origin)
            if not isinstance(args.get('control_id'), str) or args.get('action') not in {'set_value', 'click'}:
                raise PilotError('BROWSER_INVALID_ACTION')
            payload = {k: args[k] for k in ('control_id', 'action', 'value') if k in args}
        else:
            payload = {}
        self.check_before_request(transport.host_origin)
        with s.coordinator.browser_command(transport.host_origin, input=op == 'step'):
            try:
                reply = transport.request(op, payload, check_running=lambda: self.check_policy(transport.host_origin))
            except BrowserTransportError:
                if op == 'step':
                    s.coordinator.fault_browser_origin(transport.host_origin)
                raise
            if op == 'step' and reply.get('ok') and reply['result'].get('action', {}).get('status') == 'unknown':
                s.coordinator.fault_browser_origin(transport.host_origin)
        return self._result(sid, reply)

    def check_policy(self, origin):
        self.service.coordinator.ensure_running()
        self.service.access_policy.check(origin=origin, access='browser')

    def check_before_request(self, origin):
        try:
            self.service.access_policy.check(origin=origin, access='browser')
        except PilotError as error:
            error.recovery_diagnostic = {'attempt_input': 'not_sent'}
            raise

    def _result(self, sid, reply):
        result = {'session_id': sid, 'ok': reply['ok'], 'effect_verified': False}
        if reply['ok']:
            result['result'] = reply['result']
            state = reply['result'].get('state')
            if state and 'image' in state:
                result['image'] = state.pop('image')
                result['image_mime_type'] = state['image_mime_type']
        else:
            result.update(error=reply['error'], input_state=reply.get('input_state'))
        self.service.audit('browser_session_result', session_id=sid, ok=reply['ok'])
        return result

    def dispose(self):
        # Notify all children first; do not spend N deadlines before later children see EOF.
        for transport in self.sessions.values():
            transport.close(wait=False)
        return [transport.close() for transport in self.sessions.values()]
