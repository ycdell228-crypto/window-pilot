"""Explicit local application launch in an already authorized administrator context."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time

from . import win32 as w

REQUEST = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class LaunchPolicy:
    """Optional operator restrictions, not same-account malicious-code isolation."""
    def __init__(self, value):
        if (not isinstance(value, dict) or set(value) - {"enabled", "allowlist"}
                or type(value.get("enabled", True)) is not bool):
            raise w.PilotError("INVALID_APP_LAUNCH_POLICY")
        self.enabled = value.get("enabled", True)
        entries = value.get("allowlist")
        if "allowlist" in value and (not isinstance(entries, list) or any(not isinstance(p, str) for p in entries)):
            raise w.PilotError("INVALID_APP_LAUNCH_ALLOWLIST")
        self.allowlist = None if "allowlist" not in value else {w.canonical(str(local_path(p))) for p in entries}

    def check(self, executable):
        if not self.enabled:
            raise w.PilotError("APP_LAUNCH_DISABLED_BY_POLICY")
        if self.allowlist is not None and w.canonical(executable) not in self.allowlist:
            raise w.PilotError("APP_LAUNCH_NOT_ALLOWLISTED")


def local_path(value, directory=False):
    if not isinstance(value, str) or not value or "\0" in value or value.startswith("\\\\"):
        raise w.PilotError("LOCAL_ABSOLUTE_PATH_REQUIRED: no UNC/device path")
    path = Path(value)
    if not path.is_absolute() or len(path.drive) != 2 or path.drive[1] != ":":
        raise w.PilotError("LOCAL_ABSOLUTE_PATH_REQUIRED")
    try:
        path = path.resolve(strict=True)
    except OSError as exc:
        raise w.PilotError("APPLICATION_PATH_NOT_FOUND") from exc
    if len(path.drive) != 2 or str(path).startswith("\\\\"):
        raise w.PilotError("LOCAL_ABSOLUTE_PATH_REQUIRED")
    get_drive = w.api(w.K, "GetDriveTypeW", w.W.UINT, w.W.LPCWSTR)
    if get_drive(path.anchor) not in (2, 3, 5, 6):
        raise w.PilotError("APPLICATION_NETWORK_OR_UNAVAILABLE_DRIVE_REFUSED")
    if directory:
        if not path.is_dir():
            raise w.PilotError("APPLICATION_CWD_NOT_DIRECTORY")
    elif not path.is_file() or path.suffix.lower() != ".exe":
        raise w.PilotError("LOCAL_EXE_REQUIRED: not a shortcut, script or shell command string")
    return path


def plan(arguments):
    if not REQUEST.fullmatch(arguments["request_id"]):
        raise w.PilotError("INVALID_LAUNCH_REQUEST_ID: 1..64 ASCII letters/digits/_/-")
    purpose = arguments["purpose"].strip()
    if not 1 <= len(purpose) <= 300 or "\0" in purpose:
        raise w.PilotError("USER_NAMED_APPLICATION_PURPOSE_REQUIRED")
    executable = local_path(arguments["exe"])
    cwd = local_path(arguments["cwd"], True) if "cwd" in arguments else executable.parent
    argv = arguments.get("args", [])
    if (not isinstance(argv, list) or len(argv) > 128
            or any(not isinstance(v, str) or "\0" in v or len(v) > 8192 for v in argv)):
        raise w.PilotError("ARGS_STRING_ARRAY_REQUIRED: max 128, no NUL, max 8192 chars each")
    if len(subprocess.list2cmdline([str(executable), *argv]).encode("utf-16-le")) // 2 > 32760:
        raise w.PilotError("APPLICATION_ARGUMENTS_TOO_LONG")
    value = {"exe": str(executable), "args": list(argv), "cwd": str(cwd), "purpose": purpose}
    digest = hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf8")).hexdigest()
    return value, digest


def persist(path, value):
    temporary = path.with_suffix(".tmp-" + secrets.token_hex(6))
    with temporary.open("x", encoding="utf8") as file:
        json.dump(value, file, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temporary, path)


def result_error(value):
    raise w.PilotError(json.dumps(value, ensure_ascii=False))


def launch(arguments, directory, policy=None):
    policy = policy if policy is not None else LaunchPolicy({})
    if not policy.enabled:
        raise w.PilotError("APP_LAUNCH_DISABLED_BY_POLICY")
    rid = w.input_integrity(os.getpid())
    if not 0x3000 <= rid < 0x4000:
        raise w.PilotError("ADMIN_EXECUTOR_REQUIRED: no per-call UAC or direct-stdio fallback")
    value, digest = plan(arguments)
    policy.check(value["exe"])  # Before reserving request_id or creating a process.
    request_id = arguments["request_id"]
    directory = Path(directory)
    directory.mkdir(exist_ok=True)
    path = directory / (hashlib.sha256(request_id.encode("ascii")).hexdigest() + ".json")
    record = {"request_id": request_id, "plan_sha256": digest, "exe": value["exe"], "cwd": value["cwd"],
              "argument_count": len(value["args"]), "recorded_at": time.time(), "status": "reserved_before_launch",
              "new_process_created": False, "application_ready": "unverified", "window_bound": False,
              "executor": {"pid": os.getpid(), "integrity_rid": rid, **w.process_scope(os.getpid())}}
    try:
        # Atomic claim and durable receipt BEFORE CreateProcess, across clients/restarts.
        with path.open("x", encoding="utf8") as file:
            json.dump(record, file, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        try:
            old = json.loads(path.read_text(encoding="utf8"))
        except Exception:
            result_error({"request_id": request_id, "status": "launch_outcome_unknown", "retry": "never_automatic"})
        if old.get("plan_sha256") != digest:
            raise w.PilotError("LAUNCH_REQUEST_ID_REUSED_WITH_DIFFERENT_ARGUMENTS")
        if old.get("status") != "process_created":
            result_error({**old, "duplicate_request": True, "retry": "never_automatic"})
        return {**old, "new_process_created": False, "duplicate_request": True,
                "result_scope": "original_receipt_only_pid_may_have_exited_or_handed_off"}
    startup = subprocess.STARTUPINFO()
    startup.dwFlags = subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 4  # SW_SHOWNOACTIVATE; the application can independently activate.
    try:
        process = subprocess.Popen([value["exe"], *value["args"]], executable=value["exe"],
                                   cwd=value["cwd"], shell=False, startupinfo=startup,
                                   creationflags=subprocess.CREATE_NO_WINDOW,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        record.update(status="launch_failed", winerror=getattr(exc, "winerror", None), retry="never_automatic")
        persist(path, record)
        result_error(record)
    record.update(status="process_created", new_process_created=True, pid=process.pid,
                  exit_code_at_return=process.poll(), shell=False, initial_process_identity=None,
                  initial_process_security=None, focus_policy="SW_SHOWNOACTIVATE_app_may_self_activate",
                  next="list_windows then explicitly bind the actual window; launch is not application/game success")
    try:
        created, exe = w.process_identity(process.pid)
        record["initial_process_identity"] = {"pid": process.pid, "created": created, "exe": exe}
        record["initial_process_security"] = {"integrity_rid": w.input_integrity(process.pid), **w.process_scope(process.pid)}
    except w.PilotError:
        record["initial_identity_note"] = "initial process exited, handed off, or query unavailable; not proof of failure/success"
    try:
        persist(path, record)
    except Exception:
        result_error({"request_id": request_id, "pid": process.pid, "status": "process_created_receipt_commit_unknown",
                      "retry": "never_automatic", "application_ready": "unverified"})
    return record
