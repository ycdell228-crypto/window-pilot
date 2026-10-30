"""Build-time copy only: canonical runtime scripts remain in scripts/."""
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildPy(build_py):
    def run(self):
        super().run()
        scripts = Path(__file__).resolve().parent / "scripts"
        destination = Path(self.build_lib) / "window_pilot" / "_resources"
        destination.mkdir(parents=True, exist_ok=True)
        for path in [scripts / "runtime_entry.py", *sorted(scripts.glob("uia-*.ps1"))]:
            self.copy_file(str(path), str(destination / path.name))


setup(cmdclass={"build_py": BuildPy})
