"""Absolute isolated entry for scheduled executor and its fixed capture/fixture children."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True
project = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project / "src"))
dependencies = project / ".local" / "wgc-deps"
if dependencies.is_dir():
    sys.path.insert(1, str(dependencies))

if __name__ == "__main__":
    try:
        from window_pilot.__main__ import main
        main()
    except Exception as exc:
        if len(sys.argv) > 1 and sys.argv[1] == "admin-serve":
            # Fixed private diagnostic for pythonw startup; no tool payload or image content.
            import json
            import os
            import time
            directory = project / ".local" / "admin-service"
            if directory.is_dir():
                (directory / ("startup-error-" + str(os.getpid()) + ".json")).write_text(
                    json.dumps({"pid": os.getpid(), "at": time.time(), "error": str(exc)[:500], "automatic_retry": False}), encoding="utf8")
        raise
