"""Opt-in real-user concurrency check; no simulated desktop states or input.

Run with PYTHONPATH=src while the human browses/moves/switches non-target apps.
Every intentional fixture click consumes a fresh frame; errors stop the run.
"""
import argparse
import json
from pathlib import Path
import tempfile
import time

from window_pilot import win32 as w
from window_pilot.service import Service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=25)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 40:
        parser.error("use 1..40 seconds")
    observations = []
    foreground_apps = set()
    with tempfile.TemporaryDirectory(prefix="window-pilot-concurrency-") as folder:
        config = Path(folder) / "config.local.json"
        config.write_text('{"window_control":{"capture_backend":"printwindow"}}', encoding="utf8")
        service = Service(config)
        try:
            launched = service.call("launch_test", {})
            hwnd = launched["windows"][0]["hwnd"]
            service.call("list_windows", {})
            target = service.call("bind_window", {"hwnd": hwnd, "access": "observe_and_click", "purpose": "user-owned concurrency fixture validation", "capture_backend": "printwindow"})["target_id"]
            frame = service.call("observe", {"target_id": target})
            count = 0
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                result = service.call("click", {"target_id": target, "frame_id": frame["frame_id"], "x": 40, "y": 40})
                count += 1
                if w.text(hwnd) != f"Window Pilot Test | clicks={count}":
                    raise AssertionError("Fixture counter did not increase exactly once; stop without replay")
                diagnostic = result["desktop_observation"]
                observations.append(diagnostic)
                for state in (diagnostic["before"], diagnostic["after"]):
                    try:
                        foreground_apps.add(Path(w.identity(state["foreground"]).exe).name)
                    except w.PilotError:
                        pass  # a past foreground handle need not remain live
                updated = service.call("observe", {"target_id": target})
                if updated["sha256"] == frame["sha256"]:
                    raise AssertionError("Fixture image did not reflect the new click; stop without replay")
                frame = updated
                if service.faulted:
                    raise AssertionError("Input faulted")
                time.sleep(0.2)  # spacing between distinct planned clicks, never a retry
            service.call("close_test", {})
            health = service.call("health", {})
            summary = {"mode": "real desktop readings and real fixture messages; no mocks",
                       "intentional_clicks": count, "exact_counter_and_image_effects": count,
                       "clicks_with_cursor_change": sum(r["cursor_changed"] for r in observations),
                       "clicks_with_foreground_change": sum(r["foreground_changed"] for r in observations),
                       "foreground_apps_seen": sorted(foreground_apps),
                       "target_became_foreground": any(r["target_became_foreground"] for r in observations),
                       "faulted": health["faulted"],
                       "fixture_closed": health["fixture_pid"] is None}
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            if not any(r["changed"] for r in observations):
                raise SystemExit("INCONCLUSIVE: no concurrent change was observed during a click")
        finally:
            service.dispose()


if __name__ == "__main__":
    main()
