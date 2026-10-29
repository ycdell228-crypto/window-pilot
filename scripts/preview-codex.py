"""Print a disabled Codex MCP TOML entry; never register, connect or launch it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys


def main():
    project = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="Absolute path to Python 3.12+ python.exe")
    parser.add_argument("--mode", choices=("direct", "bridge"), default="direct")
    parser.add_argument("--server-name", default="window_pilot_next")
    parser.add_argument("--config", help="Existing config inside this project (direct only)")
    args = parser.parse_args()
    python = Path(args.python)
    if not python.is_absolute() or not python.is_file() or python.name.lower() != "python.exe":
        parser.error("--python must be an existing absolute python.exe path")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", args.server_name):
        parser.error("--server-name must contain 1..64 ASCII letters, digits, underscores or hyphens")
    if args.mode == "bridge" and args.config:
        parser.error("--config applies only to direct mode; bridge uses its own service manifest")

    command = ["-I", "-S", str(project / "scripts" / "runtime_entry.py")]
    notes = ["# Preview only. Review before enabling; no host configuration was changed."]
    if args.mode == "direct":
        config = Path(args.config or (project / "config.local.json"))
        if not config.is_absolute():
            config = project / config
        config = config.resolve()
        if not config.is_relative_to(project) or not config.is_file():
            parser.error("direct config must be an existing file inside this project")
        json.loads(config.read_text(encoding="utf-8-sig"))
        command += ["serve", "--config", str(config)]
        notes.append("# Direct stdio: launch_app remains unavailable; no automatic elevation.")
    else:
        manifest = project / ".local" / "admin-service" / "service.json"
        command += ["bridge", "--service-file", str(manifest)]
        notes.append("# Bridge requires a separately reviewed, installed executor for THIS project.")
        if not manifest.is_file():
            notes.append("# Service manifest is absent; this entry is not ready to enable.")
        notes.append("# This preview does not validate or connect to an executor.")

    # JSON string escaping is also valid for these TOML basic strings/arrays.
    quote = json.dumps
    print("\n".join(notes + [
        f"[mcp_servers.{args.server_name}]",
        f"command = {quote(str(python.resolve()))}",
        f"args = {quote(command)}",
        f"cwd = {quote(str(project))}",
        "enabled = false",
        "startup_timeout_sec = 20",
        "tool_timeout_sec = 30",
        f"[mcp_servers.{args.server_name}.env]",
        'PYTHONUTF8 = "1"',
        'PYTHONUNBUFFERED = "1"',
    ]))


if __name__ == "__main__":
    main()
