"""Report actual success/skip counts separately; native skips never become passes."""
import json
import os
from pathlib import Path
import sys
import unittest


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = 0

    def addSuccess(self, test):
        self.passed += 1
        super().addSuccess(test)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=2, resultclass=Result).run(suite)
    summary = {"passed": result.passed, "failed": len(result.failures), "errors": len(result.errors),
               "skipped_entries": len(result.skipped), "unexpected_successes": len(result.unexpectedSuccesses),
               "scope": "ordinary CI; native desktop entries skipped" if os.environ.get("CI") and os.environ.get("WINDOW_PILOT_NATIVE_TESTS") != "1" else "see per-test native evidence and skips"}
    directory = root / ".local/test-results"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf8") as stream:
            stream.write("### Ordinary regression checks\n\n")
            stream.write(f"Passed: {summary['passed']}; failures: {summary['failed']}; errors: {summary['errors']}; skipped entries: {summary['skipped_entries']}.\n\n")
            stream.write("Native desktop input is skipped by default. This result does not certify desktop input, administrator IPC or real-host end-to-end workflows.\n")
    print("WINDOW_PILOT_TEST_SUMMARY " + json.dumps(summary), flush=True)
    sys.exit(0 if result.wasSuccessful() else 1)
