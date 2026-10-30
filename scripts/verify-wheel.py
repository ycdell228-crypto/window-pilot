"""Install a wheel in a clean venv and exercise its real stdio/isolated worker.

--native additionally starts only the packaged project fixture, reads its UIA tree
and captures it. It never clicks, types or connects to an installed executor.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    parser.add_argument("--native", action="store_true")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    wheel, evidence = args.wheel.resolve(strict=True), args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    clean_env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    with tempfile.TemporaryDirectory(prefix="window-pilot-wheel-") as temporary:
        root = Path(temporary)
        environment = root / "environment"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / "Scripts/python.exe"
        subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--disable-pip-version-check", str(wheel)],
                       check=True, env=clean_env, cwd=root, timeout=90)
        package = environment / "Lib/site-packages/window_pilot"
        resources = package / "_resources"
        expected = {"runtime_entry.py", "uia-observe.ps1", "uia-focus.ps1", "uia-fixture.ps1", "uia-foreground-fixture.ps1"}
        if not all((resources / name).is_file() for name in expected):
            raise RuntimeError("installed wheel lacks runtime scripts")
        subprocess.run([str(python), "-I", "-S", str(resources / "runtime_entry.py"), "--help"],
                       check=True, env=clean_env, cwd=root, stdout=subprocess.DEVNULL, timeout=15)
        config = root / "config.json"
        config.write_text(json.dumps({"window_control": {"capture_backend": "printwindow"}, "app_launch": {"enabled": False}}))
        process = subprocess.Popen([str(environment / "Scripts/window-pilot.exe"), "serve", "--config", str(config)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=clean_env, cwd=root, text=True, encoding="utf8")
        replies = queue.Queue()
        def read():
            for line in process.stdout:
                replies.put(line)
            replies.put(None)
        threading.Thread(target=read, daemon=True).start()
        sequence = 0
        def rpc(method, params):
            nonlocal sequence
            sequence += 1
            process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": sequence, "method": method, "params": params}) + "\n")
            process.stdin.flush()
            line = replies.get(timeout=35)
            if not line:
                raise RuntimeError("installed stdio closed unexpectedly")
            result = json.loads(line)
            if result.get("error") or result.get("id") != sequence:
                raise RuntimeError(str(result))
            return result["result"]
        def call(name, arguments):
            result = rpc("tools/call", {"name": name, "arguments": arguments})
            if result.get("isError"):
                raise RuntimeError(str(result))
            return json.loads(result["content"][0]["text"]), result
        summary = {"wheel": wheel.name, "resources": sorted(expected), "native": args.native}
        fixture_started = False
        try:
            rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "wheel-smoke", "version": "1"}})
            tools = rpc("tools/list", {})["tools"]
            if len(tools) != 13:
                raise RuntimeError("expected 13 installed tools")
            rejected = rpc("tools/call", {"name": "launch_app", "arguments": {"exe": str(python), "purpose": "direct-mode refusal check", "request_id": "wheel-smoke-refusal"}})
            if not rejected.get("isError") or "ADMIN_EXECUTOR_REQUIRED" not in rejected["content"][0]["text"]:
                raise RuntimeError("ordinary installed stdio did not reject launch")
            summary.update(tool_count=len(tools), mode="direct_stdio", isolated_worker_import=True,
                           direct_launch_refused=True, health_checked=args.native)
            if args.native:
                health, _ = call("health", {})
                if health["app_launch"]["enabled"] or health["executor"]["mode"] != "direct_stdio":
                    raise RuntimeError("unexpected installed direct-mode health")
                fixture_started = True
                launched, _ = call("launch_test", {"kind": "uia"})
                windows, _ = call("list_windows", {})
                ids = {window["hwnd"] for window in windows["windows"]}
                selected = next(window for window in launched["windows"] if window["hwnd"] in ids)
                bound, _ = call("bind_window", {"hwnd": selected["hwnd"], "capture_backend": "printwindow"})
                observation, contents = call("observe", {"target_id": bound["target_id"]})
                image = next(item for item in contents["content"] if item["type"] == "image")
                suffix = ".png" if image["mimeType"] == "image/png" else ".jpg"
                (evidence / ("installed-fixture" + suffix)).write_bytes(base64.b64decode(image["data"]))
                controls, _ = call("observe_controls", {"target_id": bound["target_id"]})
                if not controls.get("nodes"):
                    raise RuntimeError("installed UIA worker returned no controls: " + str(controls))
                summary.update(frame_saved=observation["evidence_storage"]["saved"], uia_nodes=len(controls["nodes"]),
                               native_scope="own UIA fixture capture and read-only controls; no input, bridge or administrator installation")
            (evidence / "wheel-smoke.json").write_text(json.dumps(summary, indent=2), encoding="utf8")
            print(json.dumps(summary), flush=True)
        except Exception as exc:
            summary["error"] = str(exc)
            (evidence / "wheel-smoke-failure.json").write_text(json.dumps(summary, indent=2), encoding="utf8")
            raise
        finally:
            if fixture_started and process.poll() is None:
                try:
                    call("close_test", {})
                except Exception:
                    pass  # EOF disposal also closes only this service's project fixture.
            process.stdin.close()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            process.stdout.close()
            stderr = process.stderr.read()
            process.stderr.close()
            if stderr:
                (evidence / "stdio-stderr.txt").write_text(stderr, encoding="utf8")


if __name__ == "__main__":
    main()
