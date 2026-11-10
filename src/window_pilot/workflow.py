"""Convenience workflow delegating every input to the existing guarded service."""
import secrets
import threading
from .win32 import PilotError


class WindowWorkflow:
    def __init__(self, service):
        self.service = service
        self.sessions = {}
        self.lock = threading.Lock()

    def call(self, operation, args):
        if not self.lock.acquire(blocking=False):
            raise PilotError('WORKFLOW_BUSY')
        try:
            return getattr(self, operation)(args)
        finally:
            self.lock.release()

    def _observe(self, session):
        session['state'] = None
        state = self.service.call('get_window_state', {'target_id': session['target_id'], 'include_text': True})
        session['state'] = state
        session['state_id'] = secrets.token_hex(16)
        if state['status'] != 'ok':
            session['blocked'] = True
        return state

    def _result(self, session_id, session, state, action=None):
        result = {'session_id': session_id, 'state_id': session.get('state_id'), 'state': state,
                  'action': action, 'effect_verified': False, 'input_blocked': session['blocked']}
        if state and 'image' in state:
            # Preserve the transport's image slot without changing cached state.
            result['state'] = {k: v for k, v in state.items() if k != 'image'}
            result.update(image=state['image'], image_mime_type=state['image_mime_type'])
        return result

    def begin(self, args):
        s = self.service
        s.coordinator.ensure_running()
        # Refresh enumeration, but bind_window still verifies the exact process identity.
        s.call('list_windows', {})
        if args.get('access', 'observe') != 'observe':
            identity = s.enumerated.get(args['hwnd'])
            if identity is not None and any(
                    target == identity and s.bindings[token]['access'] != 'observe'
                    for token, target in s.targets.items()):
                # Connection-wide leases cannot be independently owned by two write bindings.
                raise PilotError('WORKFLOW_WRITE_TARGET_ALREADY_BOUND: reuse or end the existing binding')
        bind_args = {k: args[k] for k in ('hwnd', 'access', 'purpose', 'capture_backend') if k in args}
        bound = s.call('bind_window', bind_args)
        token = bound['target_id']
        session = {'target_id': token, 'access': bound['access'], 'blocked': False, 'state': None}
        session_id = secrets.token_hex(16)
        self.sessions[session_id] = session
        try:
            if session['access'] != 'observe':
                s.call('window_control', {'target_id': token, 'operation': 'acquire', 'lease_seconds': 60})
            return self._result(session_id, session, self._observe(session))
        except Exception:
            self.end({'session_id': session_id})
            raise

    def step(self, args):
        session = self.sessions.get(args['session_id'])
        if session is None:
            raise PilotError('UNKNOWN_WORKFLOW_SESSION')
        if session['blocked']:
            raise PilotError('WORKFLOW_INPUT_BLOCKED: inspect with low-level tools; never replay')
        if args['state_id'] != session.get('state_id') or session['state'] is None:
            raise PilotError('STALE_WORKFLOW_STATE')
        action_args = args['action_args']
        if not isinstance(action_args, dict):
            raise PilotError('INVALID_WORKFLOW_ACTION_ARGUMENTS')
        if set(action_args) & {'target_id', 'frame_id', 'observation_id'}:
            raise PilotError('WORKFLOW_CREDENTIAL_OVERRIDE_REFUSED')
        state = session['state']
        payload = {**action_args, 'target_id': session['target_id']}
        if args['tool'] == 'click':
            frame = state.get('screenshot')
            if not frame:
                raise PilotError('WORKFLOW_FRAME_REQUIRED')
            payload['frame_id'] = frame['frame_id']
        else:
            tree = state.get('accessibility')
            if not tree or tree['status'] != 'ok':
                raise PilotError('WORKFLOW_CONTROLS_REQUIRED')
            payload['observation_id'] = tree['observation_id']
        # Validate before consuming the wrapper state; native layer independently validates again.
        from .service import validate_arguments
        validate_arguments(args['tool'], payload)
        session['state'] = None
        result = None
        action_called = False
        try:
            self.service.call('window_control', {'target_id': session['target_id'], 'operation': 'renew', 'lease_seconds': 60})
            action_called = True
            result = self.service.call(args['tool'], payload)
            if result.get('status') == 'unknown' or self.service.recovery_status(session['target_id'])['recovery_required']:
                session['blocked'] = True
        except Exception as error:
            session['blocked'] = True
            diagnostic = getattr(error, 'recovery_diagnostic', {})
            failure = {'status': 'stopped', 'effect': 'unverified',
                      'attempt_input': diagnostic.get('attempt_input', 'unknown' if action_called else 'not_sent'),
                      'error': 'WORKFLOW_ACTION_FAILED', 'automatic_replay': False}
            result = failure if result is None else {**result, 'workflow_error': failure}
            # Exceptions do not erase the lower-level shared fault; never recover automatically.
        try:
            updated = self._observe(session)
        except Exception:
            session['blocked'] = True
            updated = None
        response = self._result(args['session_id'], session, updated, result)
        response['observation_status'] = 'ok' if updated and updated['status'] == 'ok' else 'unavailable_or_partial'
        return response

    def end(self, args):
        session_id = args['session_id']
        session = self.sessions.get(session_id)
        if session is None:
            return {'ended': True, 'already_absent': True}
        token = session['target_id']
        target = self.service.targets.get(token)
        if target is not None:
            status = self.service.coordinator.status(self.service.connection_id, target)
            other_writer = any(other != token and identity == target and
                               self.service.bindings[other]['access'] != 'observe'
                               for other, identity in self.service.targets.items())
            if session['access'] != 'observe' and status['owner_is_this_connection'] and not other_writer:
                self.service.coordinator.release(self.service.connection_id, target)
            self.service.call('unbind_window', {'target_id': token})
        self.sessions.pop(session_id, None)
        return {'ended': True, 'native_window_closed': False}
