"""Bounded read-only UI Automation. A hung provider is killed with its worker."""
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import time

from . import win32 as w
from .resources import runtime_script


def worker_diagnostics(stderr):
    events = []
    allowed = {"script_start", "assemblies_loaded", "interop_compiled", "root_resolved", "proxies_registered", "tree_read"}
    allowed.update(prefix + field for prefix in ("read_", "done_") for field in ("value", "document_text", "selected_text"))
    for line in (stderr or b"").decode("utf8", "replace").splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "UIA_STAGE" and parts[1] in allowed and parts[2].isdigit() and parts[3] in ("MTA", "STA"):
            events.append({"stage": parts[1], "elapsed_ms": int(parts[2]), "apartment": parts[3]})
    return {"stages": events, "last_stage": events[-1]["stage"] if events else "process_start_before_script_progress"}


def observe(target, max_nodes=64, max_depth=5, timeout=6, *, include_text=False, max_text_length=512, max_total_text_length=8192):
    if type(max_nodes) is not int or not 1 <= max_nodes <= 128 or type(max_depth) is not int or not 0 <= max_depth <= 8:
        raise w.PilotError("UIA_INVALID_LIMITS: max_nodes=1..128, max_depth=0..8")
    if (type(include_text) is not bool or type(max_text_length) is not int or not 1 <= max_text_length <= 2048
            or type(max_total_text_length) is not int or not 1 <= max_total_text_length <= 32768):
        raise w.PilotError("UIA_INVALID_TEXT_LIMITS")
    w.bindable(target)
    permission = w.input_access(target)
    if permission["blocked_by_integrity"]:
        raise w.PilotError("UIA_HIGHER_INTEGRITY_TARGET: no elevation or desktop fallback")
    size = w.geometry(target.hwnd)
    origin = w.W.POINT(0, 0)
    w.check(w.U.ClientToScreen(target.hwnd, w.C.byref(origin)), "UIA client origin")
    started = time.time()
    desktop_before = w.desktop_state()
    script = runtime_script("uia-observe.ps1")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    payload = {"hwnd": target.hwnd, "pid": target.pid, "max_nodes": max_nodes, "max_depth": max_depth}
    payload.update(include_text=include_text, max_text_length=max_text_length, max_total_text_length=max_total_text_length)
    try:
        worker = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-MTA", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                                input=json.dumps(payload).encode("ascii"), capture_output=True,
                                timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired as exc:
        result = {"status": "timeout", "nodes": [], "error": "UIA_TIMEOUT: worker terminated; no retry or fallback",
                  "worker_diagnostics": worker_diagnostics(exc.stderr)}
    else:
        if worker.returncode or len(worker.stdout) > 262_144:
            result = {"status": "unavailable", "nodes": [], "error": "UIA_WORKER_FAILED_OR_OUTPUT_LIMIT"}
        else:
            try:
                result = json.loads(worker.stdout.decode("utf-8-sig"))
                if not isinstance(result, dict) or result.get("status") not in {"ok", "empty", "unsupported", "unavailable", "identity_changed"}:
                    raise ValueError("invalid UIA response")
                if not isinstance(result.get("nodes"), list) or len(result["nodes"]) > max_nodes:
                    raise ValueError("invalid UIA nodes")
                for node in result["nodes"]:
                    if node["process_id"] != target.pid or not 0 <= node["depth"] <= max_depth:
                        raise ValueError("UIA scope mismatch")
            except (ValueError, KeyError, TypeError, UnicodeError):
                result = {"status": "unavailable", "nodes": [], "error": "UIA_INVALID_WORKER_RESPONSE"}
        result["worker_diagnostics"] = worker_diagnostics(worker.stderr)
    # Native identity/geometry are rechecked even after timeout or provider failure.
    w.verify(target)
    final_origin = w.W.POINT(0, 0)
    w.check(w.U.ClientToScreen(target.hwnd, w.C.byref(final_origin)), "UIA client origin after")
    if w.geometry(target.hwnd) != size or (final_origin.x, final_origin.y) != (origin.x, origin.y):
        raise w.PilotError("UIA_WINDOW_GEOMETRY_CHANGED: discard tree and observe again")
    for node in result["nodes"]:
        bounds = node["bounds_screen"]
        node["bounds_client"] = ({**bounds, "x": bounds["x"] - origin.x, "y": bounds["y"] - origin.y} if bounds else None)
    result.update(identity=asdict(target), started_at=started, finished_at=time.time(),
                  desktop_observation=w.click_desktop_diagnostic(desktop_before, w.desktop_state(), target.hwnd),
                  geometry={"x": origin.x, "y": origin.y, "width": size[0], "height": size[1]},
                  limits={"max_nodes": max_nodes, "max_depth": max_depth, "timeout_seconds": timeout},
                  coord_space="physical_pixels; bounds_client may extend outside client area",
                  scope="bound_window_control_view_same_process_only", read_only=True,
                  empty_means="no descendant controls returned; the bound root may still be included",
                  values_read=include_text and result["status"] in ("ok", "empty"), atomic_snapshot=False,
                  text_policy={"requested": include_text, "per_field_utf16_limit": max_text_length,
                               "total_utf16_limit": max_total_text_length, "max_selection_ranges": 16,
                               "selection_provider": "Win32 Edit only; other providers explicitly unsupported",
                               "scope": "per returned control; provider IsPassword filtering, not image redaction"})
    return result


ACTIONS = {"invoke", "set_value", "select", "expand", "collapse", "scroll"}
SCROLL_AMOUNTS = {"NoAmount", "SmallIncrement", "SmallDecrement", "LargeIncrement", "LargeDecrement"}


def validate_action(arguments):
    action = arguments.get("action")
    if action not in ACTIONS:
        raise w.PilotError("UIA_INVALID_ACTION")
    extras = set(arguments) - {"target_id", "observation_id", "control_id", "action"}
    if action == "set_value":
        value = arguments.get("value")
        if extras != {"value"} or not isinstance(value, str) or len(value) > 2048 or "\0" in value:
            raise w.PilotError("UIA_INVALID_VALUE: string up to 2048 characters, no NUL")
    elif action == "scroll":
        if extras - {"horizontal", "vertical"} or "value" in arguments:
            raise w.PilotError("UIA_INVALID_SCROLL")
        amounts = [arguments.get(axis, "NoAmount") for axis in ("horizontal", "vertical")]
        if any(value not in SCROLL_AMOUNTS for value in amounts) or amounts == ["NoAmount", "NoAmount"]:
            raise w.PilotError("UIA_INVALID_SCROLL: one bounded ScrollAmount step per axis")
    elif extras:
        raise w.PilotError("UIA_UNEXPECTED_ACTION_PARAMETER")


def run_action_worker(command, payload, timeout, check_running):
    if check_running is None:
        return subprocess.run(command, input=payload, capture_output=True, timeout=timeout,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    check_running()
    with subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          creationflags=subprocess.CREATE_NO_WINDOW) as process:
        deadline = time.monotonic() + timeout
        pending = payload
        try:
            while True:
                try:
                    check_running()
                except w.PilotError as exc:
                    raise ValueError("UIA_WORKER_STOPPED_OUTCOME_UNKNOWN") from exc
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(input=pending, timeout=min(0.05, remaining))
                    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                except subprocess.TimeoutExpired:
                    pending = None
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate()


def act(target, observation, node, arguments, timeout=6, *, check_running=None):
    """One provider call. Any uncertain outcome must stop input; never retry."""
    validate_action(arguments)
    w.bindable(target)
    w.require_background_target(target)
    if w.input_access(target)["blocked_by_integrity"]:
        raise w.PilotError("UIA_HIGHER_INTEGRITY_TARGET")
    own_scope, target_scope = w.process_scope(os.getpid()), w.process_scope(target.pid)
    if own_scope != target_scope:
        raise w.PilotError("UIA_PROCESS_SCOPE_MISMATCH")
    origin = w.W.POINT(0, 0)
    w.check(w.U.ClientToScreen(target.hwnd, w.C.byref(origin)), "UIA action origin")
    width, height = w.geometry(target.hwnd)
    if {"x": origin.x, "y": origin.y, "width": width, "height": height} != observation["geometry"]:
        raise w.PilotError("UIA_WINDOW_GEOMETRY_CHANGED")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    script = runtime_script("uia-observe.ps1")
    payload = {"mode": "action", "hwnd": target.hwnd, "pid": target.pid, "identity": asdict(target),
               "geometry": observation["geometry"], "expected_nodes": observation["nodes"],
               "deadline_epoch": observation["deadline_epoch"],
               "runtime_id": node["runtime_id"], **observation["limits"],
               **{key: arguments[key] for key in ("action", "value", "horizontal", "vertical") if key in arguments}}
    payload.setdefault("horizontal", "NoAmount")
    payload.setdefault("vertical", "NoAmount")
    before = w.desktop_state()
    try:
        worker = run_action_worker([str(powershell), "-NoProfile", "-NonInteractive", "-MTA", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                                   json.dumps(payload, ensure_ascii=True).encode("ascii"), timeout, check_running)
        result = json.loads(worker.stdout.decode("utf-8-sig")) if worker.returncode == 0 and len(worker.stdout) < 8192 else None
        if not isinstance(result, dict) or result.get("status") not in {"provider_returned", "rejected", "unknown"}:
            raise ValueError("invalid action reply")
        if ((result["status"] == "provider_returned" and (result.get("action_attempted") is not True or result.get("effect") != "unverified")) or
            (result["status"] == "rejected" and (result.get("action_attempted") is not False or result.get("effect") != "not_sent")) or
            (result["status"] == "unknown" and result.get("effect") != "unverified")):
            raise ValueError("inconsistent action reply")
    except (subprocess.TimeoutExpired, OSError, ValueError, UnicodeError):
        result = {"status": "unknown", "action_attempted": "unknown", "effect": "unverified",
                  "error": "UIA_ACTION_REPLY_UNKNOWN: worker stopped; never replay"}
    try:
        w.verify(target)
        result["desktop_observation"] = w.click_desktop_diagnostic(before, w.desktop_state(), target.hwnd)
    except (w.PilotError, OSError):
        result = {"status": "unknown", "action_attempted": result.get("action_attempted", "unknown"),
                  "effect": "unverified", "error": "UIA_POST_ACTION_IDENTITY_OR_DESKTOP_UNAVAILABLE",
                  "desktop_observation": {"before": before, "after": None, "unavailable": True}}
    return result
