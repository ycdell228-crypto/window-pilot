"""One real fixture click after HUMAN foreground selection; never activates a window."""
import json
from contextlib import ExitStack
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from window_pilot import win32 as w

if "--fixture" in sys.argv:
    from window_pilot.fixture import run
    run(interactive=True)
    raise SystemExit

from window_pilot.service import Service, TOOLS

report_path = ROOT / ".local" / "foreground-fixture-result.json"
report_path.parent.mkdir(exist_ok=True)
fixture = subprocess.Popen([sys.executable, "-I", "-S", "-B", str(Path(__file__).resolve()), "--fixture"],
                           creationflags=subprocess.CREATE_NO_WINDOW)
target = None
service = None
report = {"status": "starting", "fixture_pid": fixture.pid}
try:
    with ExitStack() as stack:
        directory = stack.enter_context(tempfile.TemporaryDirectory(prefix="window-pilot-foreground-"))
        config = Path(directory) / "config.local.json"
        config.write_text(json.dumps({"window_control": {"capture_backend": "printwindow"}}), encoding="utf8")
        service = Service(config)
        stack.callback(service.dispose)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            rows = [row for row in service.call("list_windows", {})["windows"]
                    if row["pid"] == fixture.pid and row["klass"] == "WindowPilotFixture"]
            if len(rows) == 1:
                target = w.identity(rows[0]["hwnd"])
                break
            time.sleep(0.1)
        if target is None:
            raise RuntimeError("Own fixture did not become available")
        bound = service.call("bind_window", {"hwnd": target.hwnd, "access": "observe_and_click",
            "purpose": "Human-authorized own-fixture foreground acceptance", "capture_backend": "printwindow"})
        token = bound["target_id"]
        report.update(status="waiting_for_human_foreground", hwnd=target.hwnd)
        report_path.write_text(json.dumps(report), encoding="utf8")
        print(json.dumps(report), flush=True)
        deadline, stable_since = time.monotonic() + 180, None
        while time.monotonic() < deadline:
            w.verify(target)
            if w.desktop_state()["foreground"] == target.hwnd:
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= 2:
                    break
            else:
                stable_since = None
            time.sleep(0.1)
        else:
            raise RuntimeError("Human foreground selection timed out; no input sent")
        initial_count = int(re.search(r"clicks=(\d+)", w.text(target.hwnd)).group(1))
        before = service.call("observe", {"target_id": token})
        result = service.call("click", {"target_id": token, "frame_id": before["frame_id"], "x": 40, "y": 40})
        after = service.call("observe", {"target_id": token})
        final_count = int(re.search(r"clicks=(\d+)", w.text(target.hwnd)).group(1))
        observation = result["desktop_observation"]
        assert result["dispatch"] == "posted" and final_count == initial_count + 1
        assert before["sha256"] != after["sha256"]
        assert observation["target_was_foreground"] and observation["target_is_foreground_after"]
        assert not observation["target_became_foreground"] and not observation["cursor_changed"]
        assert before["frame_id"] not in service.frames and not service.bindings[token]["input_faulted"]
        report.update(status="passed", initial_count=initial_count, final_count=final_count,
                      image_changed=True, frame_consumed=True, tool_count=len(TOOLS),
                      desktop_observation=observation, click_evidence=result["click_evidence"])
except Exception as exc:
    report.update(status="failed", error=str(exc))
    raise
finally:
    if target is not None and fixture.poll() is None:
        w.post(target.hwnd, 0x0010)  # close only our own tracked disposable fixture
    try:
        fixture.wait(timeout=3)
    except subprocess.TimeoutExpired:
        fixture.terminate()
        fixture.wait(timeout=3)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(report, ensure_ascii=False), flush=True)
