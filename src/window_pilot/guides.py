"""Allowlisted, read-only workflow resources; shared with the DSH skill bundle."""
from pathlib import Path

PREFIX = "window-pilot://guides/"
FILES = ("SKILL.md", "references/windows.md", "references/recovery.md", "references/browser.md")


def guide_root():
    package = Path(__file__).resolve().parent
    bundled = package / "_guides"
    return bundled if bundled.is_dir() else package.parents[1] / "dsh-plugin/skills/window-pilot"


def list_guides():
    return [{"uri": PREFIX + name, "name": name, "mimeType": "text/markdown"} for name in FILES]


def read_guide(uri):
    if not isinstance(uri, str) or uri not in {PREFIX + name for name in FILES}:
        raise ValueError("UNKNOWN_GUIDE_URI")
    return {"contents": [{"uri": uri, "mimeType": "text/markdown",
                          "text": (guide_root() / uri[len(PREFIX):]).read_text(encoding="utf8")}]}
