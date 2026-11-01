"""Bounded, revision-keyed local proof cache. No photos or font bytes leave the process."""

import copy
import json
import threading
from collections import OrderedDict
from dataclasses import asdict


def bounded_diagnostics(report, field, limit=100):
    result = copy.deepcopy(report)
    total = len(result.get(field, []))
    result[field] = result.get(field, [])[:limit]
    result[field + "_total"] = total
    result[field + "_truncated"] = total > limit
    return result


class PreviewCache:
    """Eight bounded results; serialize compiler work and reuse identical requests.

    Client cancellation stops display, not an already-running compiler subprocess.
    Compilation has its own timeout. Exceptions are never cached. Callers must
    check the stored revision again before returning a result.
    """

    def __init__(self, capacity=8, max_bytes=8_000_000):
        self.capacity, self.max_bytes = capacity, max_bytes
        self.entries = OrderedDict()
        self.lock = threading.Lock()

    def get(self, project, text, options, include_fixture, compute, *, include_generated=False):
        identity = (project["id"], project["revision"])
        key = (
            *identity,
            text,
            include_fixture,
            json.dumps(asdict(options), sort_keys=True),
            include_generated,
        )
        with self.lock:
            for old in list(self.entries):
                if old[0] == identity[0] and old[1] != identity[1]:
                    del self.entries[old]
            hit = key in self.entries
            if hit:
                self.entries.move_to_end(key)
                value = self.entries[key]
            else:
                value = compute()
                value["coverage"] = bounded_diagnostics(value["coverage"], "issues")
                value["preview"] = bounded_diagnostics(value["preview"], "diagnostics")
                if len(json.dumps(value).encode()) > self.max_bytes:
                    raise ValueError("Proof is too complex; try a shorter proof text")
                self.entries[key] = value
                while len(self.entries) > self.capacity:
                    self.entries.popitem(last=False)
            result = copy.deepcopy(value)
            result["cache"] = {"hit": hit, "project_revision": identity[1]}
            return result
