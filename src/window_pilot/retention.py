"""Bound project-owned frame evidence and audit files; never prune launch receipts."""
from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
import stat
import time


DEFAULTS = {
    "frames": {"max_files": 512, "max_bytes": 256 * 1024 * 1024, "max_age_days": 30},
    "audit": {"max_bytes": 8 * 1024 * 1024, "backups": 4},
}
FRAME_NAME = re.compile(r"[0-9a-f]{24}\.png\Z")


def settings(value):
    if not isinstance(value, Mapping) or set(value) - set(DEFAULTS):
        raise ValueError("INVALID_RETENTION_CONFIG")
    result = {}
    for section, defaults in DEFAULTS.items():
        supplied = value.get(section, {})
        if not isinstance(supplied, Mapping) or set(supplied) - set(defaults):
            raise ValueError("INVALID_RETENTION_CONFIG: " + section)
        result[section] = defaults | dict(supplied)
        for key, number in result[section].items():
            minimum = 1024 if section == "audit" and key == "max_bytes" else 1
            if type(number) is not int or number < minimum:
                raise ValueError("INVALID_RETENTION_CONFIG: " + section + "." + key)
        if section == "audit" and result[section]["backups"] > 100:
            raise ValueError("INVALID_RETENTION_CONFIG: at most 100 audit backups")
    return result


def ordinary(path, *, directory=False):
    """Refuse links/junctions instead of following them during retention."""
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("RETENTION_REPARSE_POINT_REFUSED")
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError("RETENTION_UNEXPECTED_FILE_TYPE")
    return info


class EvidenceStore:
    def __init__(self, local, config, lock):
        self.local = Path(local)
        self.config = settings(config)
        self.lock = lock  # Shared by all connections of this executor.

    def frame(self, frame_id, data):
        if not FRAME_NAME.fullmatch(frame_id + ".png"):
            raise ValueError("INVALID_EVIDENCE_FRAME_ID")
        limits = self.config["frames"]
        with self.lock:
            directory = self.local / "frames"
            ordinary(self.local, directory=True)
            directory.mkdir(exist_ok=True)
            ordinary(directory, directory=True)
            now = time.time()
            files = []
            for path in directory.iterdir():
                if FRAME_NAME.fullmatch(path.name):
                    info = ordinary(path)
                    if now - info.st_mtime > limits["max_age_days"] * 86400:
                        path.unlink()
                    else:
                        files.append((info.st_mtime_ns, path.name, path, info.st_size))
            files.sort()
            saved = len(data) <= limits["max_bytes"]
            count, size = len(files) + int(saved), sum(item[3] for item in files) + (len(data) if saved else 0)
            for _, _, path, length in files:
                if count <= limits["max_files"] and size <= limits["max_bytes"]:
                    break
                path.unlink()
                count -= 1
                size -= length
            if not saved:
                return {"saved": False, "reason": "frame_exceeds_retention_max_bytes"}
            path = directory / (frame_id + ".png")
            # Exclusive creation: no overwriting or following a pre-existing link.
            with path.open("xb") as stream:
                stream.write(data)
            return {"saved": True, "file": path.name, "policy": self.config["frames"]}

    def audit(self, row):
        data = (json.dumps(row, ensure_ascii=False) + "\n").encode("utf8")
        limits = self.config["audit"]
        if len(data) > limits["max_bytes"]:
            raise ValueError("AUDIT_RECORD_EXCEEDS_RETENTION_MAX_BYTES")
        with self.lock:
            ordinary(self.local, directory=True)
            path = self.local / "audit.jsonl"
            for candidate in self.local.iterdir():
                match = re.fullmatch(r"audit\.jsonl(?:\.([1-9][0-9]*))?", candidate.name)
                if match:
                    ordinary(candidate)
                    if match[1] is not None and int(match[1]) > limits["backups"]:
                        candidate.unlink()
                    elif candidate.stat().st_size > limits["max_bytes"]:
                        # Bound old archives too when an operator lowers the limits.
                        with candidate.open("rb") as stream:
                            stream.seek(-limits["max_bytes"] - 1, os.SEEK_END)
                            tail = stream.read().partition(b"\n")[2]
                            tail = tail[:tail.rfind(b"\n") + 1]
                        with candidate.open("wb") as stream:
                            stream.write(tail)
                            stream.flush()
                            os.fsync(stream.fileno())
            if path.exists() and path.stat().st_size + len(data) > limits["max_bytes"]:
                for index in range(limits["backups"], 0, -1):
                    source = path if index == 1 else self.local / ("audit.jsonl." + str(index - 1))
                    if source.exists():
                        os.replace(source, self.local / ("audit.jsonl." + str(index)))
            with path.open("ab") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
