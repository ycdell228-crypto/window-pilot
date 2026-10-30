"""Real temporary files verify bounded evidence, complete audit rows and receipt survival."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest

from window_pilot.retention import EvidenceStore


class RetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.local = Path(self.temp.name)
        self.lock = threading.Lock()

    def store(self, **options):
        return EvidenceStore(self.local, options, self.lock)

    def test_frames_keep_newest_with_count_bytes_and_age_bounds(self):
        store = self.store(frames={"max_files": 2, "max_bytes": 10, "max_age_days": 1})
        store.frame("0" * 24, b"old")
        old = self.local / "frames" / ("0" * 24 + ".png")
        os.utime(old, (time.time() - 2 * 86400,) * 2)
        store.frame("1" * 24, b"1111")
        store.frame("2" * 24, b"2222")
        store.frame("3" * 24, b"333333")
        paths = sorted((self.local / "frames").glob("*.png"))
        self.assertEqual([p.read_bytes() for p in paths], [b"2222", b"333333"])
        self.assertFalse(old.exists())
        store.frame("4" * 24, b"4444444444")
        self.assertEqual([p.read_bytes() for p in (self.local / "frames").glob("*.png")], [b"4444444444"])

    def test_oversize_frame_reported_and_receipts_and_other_files_untouched(self):
        receipt = self.local / "app-launches" / "receipt.json"
        receipt.parent.mkdir()
        receipt.write_bytes(b"durable request-id claim")
        directory = self.local / "frames"
        directory.mkdir()
        foreign = directory / "manual.png"
        foreign.write_bytes(b"not a generated frame")
        result = self.store(frames={"max_bytes": 3}).frame("a" * 24, b"1234")
        self.assertFalse(result["saved"])
        self.assertEqual(receipt.read_bytes(), b"durable request-id claim")
        self.assertEqual(foreign.read_bytes(), b"not a generated frame")
        self.assertFalse((directory / ("a" * 24 + ".png")).exists())

    def test_concurrent_audit_rotation_is_bounded_and_latest_rows_readable(self):
        stores = [self.store(audit={"max_bytes": 1024, "backups": 2}) for _ in range(2)]
        def write(index):
            stores[index % 2].audit({"index": index, "text": "中" * 200})
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(write, range(12)))
        stores[0].audit({"index": "last", "text": "中" * 200})
        paths = list(self.local.glob("audit.jsonl*"))
        self.assertEqual(len(paths), 3)
        for path in paths:
            self.assertLessEqual(path.stat().st_size, 1024)
            for line in path.read_text(encoding="utf8").splitlines():
                json.loads(line)
        self.assertEqual(json.loads((self.local / "audit.jsonl").read_text(encoding="utf8"))["index"], "last")

    def test_legacy_oversize_audit_keeps_complete_recent_records(self):
        path = self.local / "audit.jsonl"
        path.write_text("".join(json.dumps({"i": i, "text": "x" * 200}) + "\n" for i in range(20)), encoding="utf8")
        self.store(audit={"max_bytes": 1024, "backups": 2}).audit({"i": 20, "text": "x" * 500})
        archive = self.local / "audit.jsonl.1"
        self.assertLessEqual(archive.stat().st_size, 1024)
        rows = [json.loads(line) for line in archive.read_text(encoding="utf8").splitlines()]
        self.assertEqual(rows[-1]["i"], 19)
        self.assertEqual(json.loads(path.read_text(encoding="utf8"))["i"], 20)

    def test_bad_retention_config_rejected_without_files_changed(self):
        for value in ({"frames": {"max_files": 0}}, {"audit": {"backups": True}}, {"frames": {"typo": 1}}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                EvidenceStore(self.local, value, self.lock)
        self.assertEqual(list(self.local.iterdir()), [])

    def test_lowered_limits_prune_old_archives_and_bound_corrupt_legacy_tail(self):
        for index in range(1, 5):
            (self.local / ("audit.jsonl." + str(index))).write_bytes(b"x" * 4096)
        (self.local / "audit.jsonl").write_bytes(b"x" * 4096)
        self.store(audit={"max_bytes": 1024, "backups": 2}).audit({"new": True})
        paths = list(self.local.glob("audit.jsonl*"))
        self.assertEqual(len(paths), 3)
        self.assertTrue(all(p.stat().st_size <= 1024 for p in paths))
        self.assertEqual(json.loads((self.local / "audit.jsonl").read_text()), {"new": True})
