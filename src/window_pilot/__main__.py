from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def serve(config):
    from .service import Service
    from .rpc import Dispatcher, stdio_loop
    service = Service(config)
    try:
        stdio_loop(Dispatcher(service).handle)
    finally:
        service.dispose()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["serve", "bridge", "admin-serve", "executor-status", "executor-stop", "fixture", "_capture"])
    parser.add_argument("payload", nargs="?")
    parser.add_argument("--config", default="config.local.json")
    parser.add_argument("--service-file", default=str(Path(__file__).resolve().parents[2] / ".local/admin-service/service.json"))
    parser.add_argument("--backend", choices=["printwindow", "wgc"], default="printwindow")
    args = parser.parse_args()
    if args.command == "serve":
        serve(Path(args.config).resolve())
    elif args.command == "bridge":
        from .admin_service import bridge
        bridge(args.service_file)
    elif args.command == "admin-serve":
        from .admin_service import run
        run(args.service_file)
    elif args.command in ("executor-status", "executor-stop"):
        from .admin_service import operator
        value = operator(args.service_file, "status" if args.command == "executor-status" else "stop")
        print(json.dumps(value, ensure_ascii=False))
    elif args.command == "fixture":
        from .fixture import run
        run()
    else:
        from .win32 import Identity, capture_worker
        try:
            if args.backend == "wgc":
                from .wgc import capture_worker
            data = capture_worker(Identity(**json.loads(args.payload)))
            sys.stdout.buffer.write(data)
        except Exception as exc:
            sys.stderr.buffer.write(str(exc).encode("utf8"))
            sys.exit(1)


if __name__ == "__main__":
    main()
