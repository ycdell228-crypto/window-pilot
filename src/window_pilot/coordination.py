"""Executor-local ownership, observation epochs and uncertain-input fault gates."""
from dataclasses import dataclass
from contextlib import contextmanager
import threading
import secrets
import time
from .win32 import PilotError


@dataclass(frozen=True)
class WindowKey:
    hwnd: int
    pid: int
    created: int
    exe: str
    tid: int
    klass: str

    @classmethod
    def from_identity(cls, identity):
        return cls(**{name: getattr(identity, name) for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class ObservationStamp:
    window: WindowKey
    epoch: int


class CoordinationError(PilotError):
    pass


@dataclass
class WindowState:
    epoch: int = 0
    owner: str | None = None
    deadline: float | None = None
    active: object | None = None
    disconnect_pending: bool = False
    fault: str | None = None
    unobserved_input: bool = False
    input_state: str = "no_input_recorded"


@dataclass
class InputTicket:
    window: WindowKey
    connection: str
    started: bool = False
    outcome_known: bool = False
    sent: bool = False
    unknown: bool = False

    def outcome(self, *, sent, unknown=False):
        self.outcome_known, self.sent, self.unknown = True, sent, unknown


class Coordinator:
    def __init__(self, *, shared=True, clock=time.monotonic):
        self.shared = shared
        self.clock = clock
        self._lock = threading.RLock()
        self.audit_lock = threading.Lock()
        self._windows = {}
        self._closed = set()
        self._foreground = False
        self._background = 0
        self._stop_id = None
        self._browser_workers = {}
        self._browser_active = 0
        self._browser_faults = set()
        self._browser_origins_active = set()

    def require_browser_origin(self, origin):
        with self._lock:
            if origin in self._browser_faults:
                raise CoordinationError('BROWSER_ORIGIN_INPUT_UNKNOWN: no new session or replay; manual review required')

    def fault_browser_origin(self, origin):
        with self._lock:
            self._browser_faults.add(origin)

    def register_browser(self, key, cancel, exited):
        with self._lock:
            self.ensure_running()
            self._browser_workers = {k: v for k, v in self._browser_workers.items() if not v[1]()}
            if len(self._browser_workers) >= 32:
                raise CoordinationError('BROWSER_EXECUTOR_CAPACITY')
            self._browser_workers[key] = (cancel, exited)

    @contextmanager
    def browser_command(self, origin=None, *, input=True):
        with self._lock:
            self.ensure_running()
            if input and origin is not None:
                self.require_browser_origin(origin)
            if origin is not None and origin in self._browser_origins_active:
                raise CoordinationError('BROWSER_ORIGIN_OPERATION_IN_FLIGHT')
            if self._foreground:
                raise CoordinationError('FOREGROUND_INPUT_IN_FLIGHT')
            if origin is not None:
                self._browser_origins_active.add(origin)
            self._background += 1
            self._browser_active += 1
        try:
            yield
        finally:
            with self._lock:
                self._background -= 1
                self._browser_active -= 1
                self._browser_origins_active.discard(origin)

    def ensure_running(self):
        with self._lock:
            if self._stop_id is not None:
                raise CoordinationError("EXECUTOR_STOPPED: explicit user-requested resume required; no replay")

    def stop_status(self):
        with self._lock:
            return {"stopped": self._stop_id is not None, "stop_id": self._stop_id,
                    "in_flight": self._browser_active + sum(state.active is not None for state in self._windows.values()),
                    "browser_cleanup_pending": sum(not exited() for _, exited in self._browser_workers.values()) if self._stop_id else 0,
                    "scope": "all input connections in this executor; not other executors",
                    "read_only_observation_allowed": True}

    def stop_input(self):
        with self._lock:
            created_by_this_call = self._stop_id is None
            if self._stop_id is None:
                self._stop_id = secrets.token_hex(16)
                for state in self._windows.values():
                    state.epoch += 1
            workers = list(self._browser_workers.values())
            receipt = {**self.stop_status(), 'created_by_this_call': created_by_this_call}
        # Do not hold the coordinator lock while notifying a process of cancellation.
        for cancel, _ in workers:
            cancel()
        return receipt

    def resume_input(self, stop_id):
        with self._lock:
            if self._stop_id is None or stop_id != self._stop_id:
                raise CoordinationError("STOP_ID_MISMATCH: read current stop status")
            if (self._browser_active or any(state.active is not None for state in self._windows.values())
                    or any(not exited() for _, exited in self._browser_workers.values())):
                raise CoordinationError("STOP_STILL_IN_FLIGHT: wait for native work and cleanup")
            self._stop_id = None
            for state in self._windows.values():
                state.epoch += 1
            return {**self.stop_status(), "next": "acquire/observe anew; existing input faults still require reviewed recovery"}

    def _state(self, key):
        if key not in self._windows:
            if len(self._windows) >= 4096:
                raise CoordinationError("WINDOW_COORDINATION_CAPACITY")
            self._windows[key] = WindowState()
        state = self._windows[key]
        if state.active is None and state.deadline is not None and self.clock() >= state.deadline:
            self._drop(state, "lease_expired")
        return state

    def _drop(self, state, reason):
        if state.unobserved_input:
            state.fault = state.fault or ("unreviewed_input_on_" + reason)
        state.owner = state.deadline = None
        state.disconnect_pending = False
        state.epoch += 1

    def _owner(self, state, connection):
        if connection in self._closed:
            raise CoordinationError("CONNECTION_CLOSED")
        if state.owner != connection:
            raise CoordinationError("WINDOW_NOT_OWNER: acquire control explicitly")

    def _duration(self, seconds):
        if seconds is None and not self.shared:
            return None  # direct stdio's one connection owns until explicit release/dispose
        if type(seconds) is not int or not 10 <= seconds <= 120:
            raise CoordinationError("INVALID_LEASE_SECONDS: 10..120")
        return self.clock() + seconds

    def acquire(self, connection, identity, seconds=60):
        with self._lock:
            deadline = self._duration(seconds)
            if connection in self._closed:
                raise CoordinationError("CONNECTION_CLOSED")
            state = self._state(WindowKey.from_identity(identity))
            if state.active is not None:
                raise CoordinationError("WINDOW_ACTION_IN_FLIGHT")
            if state.owner not in (None, connection):
                raise CoordinationError("WINDOW_OWNED_BY_ANOTHER_CONNECTION")
            if state.owner is None:
                state.epoch += 1
            state.owner, state.deadline = connection, deadline
            return self._status(state, connection)

    def renew(self, connection, identity, seconds=60):
        with self._lock:
            state = self._state(WindowKey.from_identity(identity))
            self._owner(state, connection)
            state.deadline = self._duration(seconds)
            return self._status(state, connection)

    def release(self, connection, identity):
        with self._lock:
            state = self._state(WindowKey.from_identity(identity))
            self._owner(state, connection)
            if state.active is not None:
                raise CoordinationError("WINDOW_ACTION_IN_FLIGHT")
            self._drop(state, "release")
            return self._status(state, connection)

    def _status(self, state, connection):
        return {"epoch": state.epoch, "owned": state.owner is not None,
                "owner_is_this_connection": state.owner == connection, "in_flight": state.active is not None,
                "lease_remaining_seconds": max(0, state.deadline - self.clock()) if state.deadline is not None else None,
                "faulted": state.fault is not None, "fault": state.fault,
                "unobserved_input": state.unobserved_input, "input_state": state.input_state,
                "shared_executor": self.shared}

    def status(self, connection, identity):
        with self._lock:
            return self._status(self._state(WindowKey.from_identity(identity)), connection)

    def observe_begin(self, identity):
        with self._lock:
            key = WindowKey.from_identity(identity)
            state = self._state(key)
            if state.active is not None:
                raise CoordinationError("WINDOW_ACTION_IN_FLIGHT: read again after it finishes")
            return ObservationStamp(key, state.epoch)

    def validate_stamp(self, identity, stamp, ticket=None):
        with self._lock:
            key = WindowKey.from_identity(identity)
            state = self._state(key)
            if not isinstance(stamp, ObservationStamp) or stamp.window != key or stamp.epoch != state.epoch:
                raise CoordinationError("WINDOW_OBSERVATION_INVALIDATED: new observation required")
            if state.active is not None and state.active is not ticket:
                raise CoordinationError("WINDOW_ACTION_IN_FLIGHT")
            return state

    def observe_end(self, connection, identity, stamp):
        with self._lock:
            state = self.validate_stamp(identity, stamp)
            if state.owner == connection and state.fault is None:
                if state.unobserved_input:
                    state.input_state = "observation_available"
                state.unobserved_input = False

    def recover(self, connection, identity, stamp):
        with self._lock:
            state = self.validate_stamp(identity, stamp)
            self._owner(state, connection)
            if state.active is not None:
                raise CoordinationError("WINDOW_ACTION_IN_FLIGHT")
            state.fault = None
            state.unobserved_input = False
            state.input_state = "reviewed_no_replay"
            state.epoch += 1  # even the reviewed observation is not reusable for input
            return self._status(state, connection)

    def disconnect(self, connection):
        with self._lock:
            self._closed.add(connection)
            for state in self._windows.values():
                if state.owner == connection:
                    if state.active is not None:
                        state.disconnect_pending = True
                        state.epoch += 1
                    else:
                        self._drop(state, "disconnect")

    @contextmanager
    def command(self, connection, identity, *, foreground=False):
        key = WindowKey.from_identity(identity)
        with self._lock:
            self.ensure_running()
            state = self._state(key)
            self._owner(state, connection)
            if state.fault is not None:
                raise CoordinationError("WINDOW_INPUT_FAULTED (BINDING_INPUT_FAULTED): explicit reviewed recovery required")
            if state.active is not None:
                raise CoordinationError("WINDOW_ACTION_IN_FLIGHT")
            if self._foreground or (foreground and self._background):
                raise CoordinationError("DESKTOP_INPUT_BUSY")
            if foreground:
                self._foreground = True
            else:
                self._background += 1
            ticket = InputTicket(key, connection)
            state.active = ticket
        failed = False
        try:
            yield ticket
        except BaseException:
            failed = True
            raise
        finally:
            with self._lock:
                # Do not expire/release a lease until all native work/audit has finished.
                state = self._windows[key]
                if ticket.started:
                    uncertain = ticket.unknown or not ticket.outcome_known or (failed and ticket.sent)
                    if uncertain:
                        state.fault = "input_outcome_unknown"
                        state.epoch += 1
                        state.unobserved_input = True
                        state.input_state = "partial_or_unknown"
                    else:
                        state.unobserved_input = ticket.sent
                        state.input_state = "sent_unreviewed" if ticket.sent else "not_sent"
                state.active = None
                if foreground:
                    self._foreground = False
                else:
                    self._background -= 1
                if state.disconnect_pending:
                    self._drop(state, "disconnect")
                elif state.deadline is not None and self.clock() >= state.deadline:
                    self._drop(state, "lease_expired")

    def begin_input(self, ticket, identity, stamp):
        with self._lock:
            self.ensure_running()
            state = self.validate_stamp(identity, stamp, ticket)
            self._owner(state, ticket.connection)
            if state.active is not ticket or ticket.started:
                raise CoordinationError("INVALID_INPUT_TICKET")
            if state.fault is not None:
                raise CoordinationError("WINDOW_INPUT_FAULTED")
            ticket.started = True
            state.unobserved_input = True
            state.epoch += 1
