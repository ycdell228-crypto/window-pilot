"""Persistent same-user interactive administrator executor; normal stdio bridge."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

from . import win32 as w
from . import local_pipe
from .rpc import Dispatcher, METHODS, error, stdio_loop
from .service import Service


def atomic(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")
    os.replace(temporary, path)


def identity():
    created, exe = w.process_identity(os.getpid())
    rid = w.input_integrity(os.getpid())
    return {"pid": os.getpid(), "created": created, "exe": exe, **w.process_scope(os.getpid()),
            "integrity_rid": rid, "is_administrator": 0x3000 <= rid < 0x4000}


def source_digest(service_file):
    root = Path(__file__).resolve().parents[2]
    paths = sorted(Path(__file__).parent.glob("*.py")) + [root / "scripts/runtime_entry.py", Path(service_file)]
    value = hashlib.sha256()
    for path in paths:
        value.update(str(path).encode("utf8"))
        value.update(path.read_bytes())
    return value.hexdigest()


def settings(path):
    path = Path(path).resolve()
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    root = Path(__file__).resolve().parents[2]
    if (Path(value["project"]).resolve() != root or not Path(value["config"]).resolve().is_relative_to(root)
            or Path(sys.executable).resolve() not in (Path(value["python"]).resolve(), Path(value["executor_python"]).resolve())
            or not value["pipe_base"].startswith("\\\\.\\pipe\\WindowPilot.")):
        raise w.PilotError("ADMIN_SERVICE_CONFIGURATION_MISMATCH")
    own = identity()
    if own["sid"] != value["user_sid"] or own["session"] == 0:
        raise w.PilotError("ADMIN_SERVICE_REQUIRES_SAME_USER_INTERACTIVE_SESSION")
    value["pipe"] = value["pipe_base"] + "." + str(own["session"])
    value["runtime"] = path.parent
    return value, own


def peer(connection, own, server_side, expected_python):
    other = connection.peer(server_side)
    if (other["sid"] != own["sid"] or other["session"] != own["session"]
            or (not server_side and (not 0x3000 <= other["integrity_rid"] < 0x4000
                                    or w.canonical(other["exe"]) != w.canonical(expected_python)))):
        raise w.PilotError("PIPE_PEER_REJECTED: same user/session and actual high-integrity executor required")
    return other


def bridge(service_file):
    config, own = settings(service_file)
    connection = local_pipe.connect(config["pipe"])
    try:
        peer(connection, own, False, config["executor_python"])
        def forward(request):
            if not isinstance(request, dict) or request.get("jsonrpc") != "2.0":
                return error(None, -32600, "Invalid request")
            if "id" not in request:
                return None  # initialized/cancel notifications cannot perform actions
            if request.get("method") not in METHODS:
                return error(request.get("id"), -32601, "Method not found")
            try:
                connection.send(request)
                response = connection.receive(25)
                if not isinstance(response, dict) or response.get("id") != request.get("id"):
                    raise w.PilotError("EXECUTOR_RESPONSE_ID_MISMATCH")
                return response
            except Exception as exc:
                # Exit this bridge; don't reconnect/fallback/resend even if the host restarts it.
                raise w.PilotError(f"EXECUTOR_CONNECTION_LOST: last action may have run; NEVER replay or restore tokens; {exc}") from exc
        stdio_loop(forward)
    finally:
        connection.close()


def operator(service_file, action):
    config, own = settings(service_file)
    connection = local_pipe.connect(config["pipe"])
    try:
        server = peer(connection, own, False, config["executor_python"])
        if action == "stop":
            connection.send({"control": "stop"})
            return connection.receive(10)
        connection.send({"jsonrpc": "2.0", "id": "operator-health", "method": "tools/call",
                         "params": {"name": "health", "arguments": {}}})
        response = connection.receive(10)
        if response.get("result", {}).get("isError") is not False:
            raise w.PilotError("EXECUTOR_HEALTH_FAILED")
        return {"connected": True, "actual_server": server,
                "health": json.loads(response["result"]["content"][0]["text"])}
    finally:
        connection.close()


def run(service_file):
    config, own = settings(service_file)
    if not own["is_administrator"] or w.canonical(own["exe"]) != w.canonical(config["executor_python"]):
        raise w.PilotError("ADMIN_EXECUTOR_NOT_ELEVATED: use the separately approved logon task; no automatic UAC")
    runtime = config["runtime"]
    sessions = runtime / "sessions"
    sessions.mkdir(exist_ok=True)
    import msvcrt
    lock = (runtime / ("executor-" + str(own["session"]) + ".lock")).open("a+b")
    lock.seek(0)
    if not lock.read(1):
        lock.write(b"0"); lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError as exc:
        lock.close()
        raise w.PilotError("ADMIN_EXECUTOR_ALREADY_RUNNING") from exc
    stopped, operations, state_lock = threading.Event(), threading.Lock(), threading.Lock()
    digest = source_digest(service_file)
    stop_reason = {"value": "operator_stop_or_connection_shutdown"}
    instance = secrets.token_hex(12)
    clients, clients_lock = set(), threading.Lock()
    state_path = runtime / ("status-" + str(own["session"]) + ".json")

    def state(status):
        with state_lock:
            atomic(state_path, {"status": status, "instance_id": instance, "executor": own,
                                "heartbeat_at": time.time(), "pipe": config["pipe"], "task_name": config["task_name"],
                                "code_sha256": digest, "stop_reason": stop_reason["value"] if stopped.is_set() else None})

    def heartbeat():
        while not stopped.wait(2):
            try:
                if source_digest(service_file) != digest:
                    raise w.PilotError("source or manifest changed")
            except Exception:
                stop_reason["value"] = "source_or_manifest_changed_no_resume"
                stopped.set()
                return
            state("ready")

    def client(connection):
        service = None
        try:
            other = peer(connection, own, True, config["python"])
            session_id = secrets.token_hex(12)
            service = Service(config["config"], lock_path=sessions / (session_id + ".lock"), allow_app_launch=True)
            executor = {**own, "mode": "administrator_service", "instance_id": instance, "connection_id": session_id,
                        "code_sha256": digest,
                        "client_pid": other["pid"], "client_integrity_rid": other["integrity_rid"],
                        "transport": "same_user_same_session_local_named_pipe"}
            dispatch = Dispatcher(service, executor)
            while not stopped.is_set():
                request = connection.receive()
                if request == {"control": "stop"}:
                    connection.send({"stopped": True, "bound_user_windows_untouched": True, "automatic_restart": False})
                    stopped.set()
                    return
                with operations:  # no concurrent native actions across MCP clients
                    if stopped.is_set():
                        return
                    if source_digest(service_file) != digest:
                        stop_reason["value"] = "source_or_manifest_changed_no_resume"
                        stopped.set()
                        connection.send(error(request.get("id") if isinstance(request, dict) else None, -32001,
                                              "Executor changed; old tokens invalid. Never replay actions."))
                        return
                    response = dispatch.handle(request)
                if response is not None:
                    connection.send(response)
        except (EOFError, w.PilotError, ValueError):
            pass  # close connection; never resend, restore frames or continue its actions
        finally:
            if service:
                service.dispose()  # only its project fixture, never any bound user app
            connection.close()
            with clients_lock:
                clients.discard(threading.current_thread())

    first = True
    try:
        state("starting")
        threading.Thread(target=heartbeat, daemon=True).start()
        while not stopped.is_set():
            connection = local_pipe.listen(config["pipe"], own["sid"], stopped, first)
            first = False
            state("ready")
            with clients_lock:
                if len(clients) >= 4:
                    connection.close()
                    continue
                thread = threading.Thread(target=client, args=(connection,), daemon=True)
                clients.add(thread)
            thread.start()
    except w.PilotError:
        if not stopped.is_set():
            raise
    finally:
        stopped.set()
        with clients_lock:
            remaining = list(clients)
        for thread in remaining:
            thread.join(timeout=3)
        state("stopped_no_resume")
        lock.close()
