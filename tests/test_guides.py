"""Workflow guides must be reachable over real MCP without dispatching app actions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(sys.platform == "win32", "server requires Windows")
class GuideTests(unittest.TestCase):
    def test_stdio_guides_and_rejected_arbitrary_file_read(self):
        project = Path(__file__).resolve().parents[1]
        uris = ["window-pilot://guides/" + name for name in
                ("SKILL.md", "references/windows.md", "references/recovery.md", "references/browser.md")]
        calls = [("initialize", {}), ("tools/list", {}), ("resources/list", {}),
                 ("resources/templates/list", {})]
        calls += [("resources/read", {"uri": uri}) for uri in uris]
        calls += [("resources/read", {"uri": uri}) for uri in
                  ("window-pilot://guides/../config.local.json", "file:///C:/Windows/win.ini", None)]
        calls += [("ping", {})]
        requests = [{"jsonrpc": "2.0", "id": index, "method": method, "params": params}
                    for index, (method, params) in enumerate(calls, 1)]
        with tempfile.TemporaryDirectory() as folder:
            config = Path(folder) / "config.json"
            config.write_text((project / "config.example.json").read_text(encoding="utf8"), encoding="utf8")
            result = subprocess.run(
                [sys.executable, "-I", "-S", str(project / "scripts/runtime_entry.py"),
                 "serve", "--config", str(config)], cwd=project,
                input="".join(json.dumps(row) + "\n" for row in requests).encode(),
                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([row["id"] for row in replies], list(range(1, len(requests) + 1)))
        self.assertIn("resources", replies[0]["result"]["capabilities"])
        self.assertEqual(len(replies[1]["result"]["tools"]), 15)
        self.assertEqual([row["uri"] for row in replies[2]["result"]["resources"]], uris)
        self.assertEqual(replies[3]["result"], {"resourceTemplates": []})
        for reply, uri in zip(replies[4:8], uris):
            content = reply["result"]["contents"][0]
            self.assertEqual(content["uri"], uri)
            self.assertEqual(content["mimeType"], "text/markdown")
            source = project / "dsh-plugin/skills/window-pilot" / uri.removeprefix("window-pilot://guides/")
            self.assertEqual(content["text"], source.read_text(encoding="utf8"))
        for reply in replies[8:11]:
            self.assertIn("UNKNOWN_GUIDE_URI", reply["error"]["message"])
        self.assertEqual(replies[11]["result"], {})
