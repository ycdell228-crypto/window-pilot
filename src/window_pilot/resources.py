"""Locate immutable runtime scripts in a source checkout or an installed wheel."""
from pathlib import Path


def runtime_script(name):
    if name not in {"runtime_entry.py", "uia-observe.ps1", "uia-focus.ps1", "uia-fixture.ps1", "uia-foreground-fixture.ps1"}:
        raise ValueError("UNKNOWN_RUNTIME_RESOURCE")
    package = Path(__file__).resolve().parent
    bundled = package / "_resources" / name
    source = package.parents[1] / "scripts" / name
    path = bundled if bundled.is_file() else source
    if not path.is_file():
        raise FileNotFoundError("RUNTIME_RESOURCE_MISSING: " + name)
    return path
