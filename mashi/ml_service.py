"""Opt-in configured checkpoint, isolated bounded workers and retained source terms."""

import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time


LICENSE_ROOT = Path(__file__).parent / "licenses" / "ml"


def source_terms(digest):
    data = (LICENSE_ROOT / "source.json").read_bytes()
    manifest = json.loads(data)
    if (
        hashlib.sha256((LICENSE_ROOT / "corpus.lock.json").read_bytes()).hexdigest()
        != manifest["corpus_manifest_sha256"]
    ):
        raise ValueError("Model source manifest changed; generated-font export is blocked")
    for font in manifest["fonts"]:
        notice = LICENSE_ROOT / font["notice"]
        if (
            not notice.is_file()
            or hashlib.sha256(notice.read_bytes()).hexdigest() != font["notice_sha256"]
        ):
            raise ValueError(
                "Source font notices are missing or changed; generated-font export is blocked"
            )
    known = digest in manifest["checkpoints"]
    return {
        "font_license": "OFL-1.1" if known else "unclassified; font export blocked",
        "source_manifest_sha256": hashlib.sha256(data).hexdigest(),
        "checkpoint_source_known": known,
        "checkpoint_distribution": "unresolved; no unrestricted weight redistribution licence asserted",
        "source_repository": manifest["repository"] if known else "unclassified",
        "source_commit": manifest["commit"] if known else "unclassified",
        "source_families": [font["family"] for font in manifest["fonts"]] if known else [],
        "notices": manifest["fonts"] if known else [],
        "ofl_faq": "https://openfontlicense.org/ofl-faq/#1_25",
    }


class CompletionService:
    def __init__(self, path=None, digest=None):
        self.path = (
            Path(path or os.environ["MASHI_COMPLETION_CHECKPOINT"]).expanduser().resolve()
            if path or os.environ.get("MASHI_COMPLETION_CHECKPOINT")
            else None
        )
        self.digest = digest or os.environ.get("MASHI_COMPLETION_SHA256", "")
        self.model = None
        self.guard = threading.Lock()
        self.active = None
        self.canceled = {}
        self.loaded_by = None
        self.epoch = 0

    def capabilities(self):
        configured = bool(self.path and re.fullmatch("[a-f0-9]{64}", self.digest))
        available = configured and importlib.util.find_spec("scipy") is not None
        return {
            "configured": configured,
            "available": available,
            "loaded": self.model is not None,
            "model": self.model,
            "profile": "configured-local-checkpoint" if configured else None,
            "filename": self.path.name if configured else None,
            "reason": "Choose and load the configured checkpoint."
            if available
            else "Completion is unavailable. Configure a local checkpoint and SHA-256, and install the completion extra. Manual capture and export remain available.",
        }

    def cancel(self, project_id, job_id):
        with self.guard:
            now = time.monotonic()
            self.canceled = {key: at for key, at in self.canceled.items() if now - at < 90}
            self.canceled[(project_id, job_id)] = now
            if self.loaded_by == (project_id, job_id):
                self.model, self.loaded_by = None, None
                self.epoch += 1
            if len(self.canceled) > 128:
                self.canceled.pop(next(iter(self.canceled)))
            if (
                self.active
                and self.active["project"] == project_id
                and self.active["job"] == job_id
            ):
                self.active["canceled"] = True
                if self.active["process"]:
                    self.active["process"].terminate()

    def worker(self, operation, project_id, job_id, **data):
        if not self.capabilities()["available"]:
            raise ValueError(self.capabilities()["reason"])
        with self.guard:
            if self.active:
                raise ValueError(
                    "A completion request is already running. Cancel it or retry shortly."
                )
            if (project_id, job_id) in self.canceled:
                raise ValueError("Completion request canceled")
            state = {"project": project_id, "job": job_id, "process": None, "canceled": False}
            self.active = state
        try:
            environment = dict(os.environ)
            for name in [
                "OPENBLAS_NUM_THREADS",
                "OMP_NUM_THREADS",
                "VECLIB_MAXIMUM_THREADS",
                "MKL_NUM_THREADS",
            ]:
                environment[name] = "1"
            request = {
                "operation": operation,
                "checkpoint": str(self.path),
                "sha256": self.digest,
                **data,
            }
            with self.guard:
                if state["canceled"]:
                    raise ValueError("Completion request canceled")
                process = subprocess.Popen(
                    [sys.executable, "-m", "mashi.ml_engine"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=Path(__file__).parent.parent,
                    env=environment,
                )
                state["process"] = process
            try:
                output, errors = process.communicate(json.dumps(request), timeout=45)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise ValueError(
                    "Completion exceeded 45 seconds. Reduce references or retry."
                ) from None
            if state["canceled"]:
                raise ValueError("Completion request canceled")
            if len(output) > 2_000_000:
                raise ValueError("Completion response exceeds its size limit")
            try:
                result = json.loads(output)
            except ValueError:
                raise ValueError(
                    "Completion worker failed. Manual capture/export are still available."
                ) from None
            if process.returncode or "error" in result:
                raise ValueError(result.get("error", "Completion failed"))
            result["model"]["terms"] = source_terms(self.digest)
            return result
        except OSError as error:
            raise ValueError(
                "Completion worker could not start or finish. Check the optional installation; manual capture/export remain available."
            ) from error
        finally:
            with self.guard:
                self.active = None

    def load(self, project_id, job_id):
        epoch = self.epoch
        result = self.worker("inspect", project_id, job_id)
        with self.guard:
            if epoch != self.epoch or (project_id, job_id) in self.canceled:
                raise ValueError("Checkpoint load canceled")
            self.model = result["model"]
            self.loaded_by = (project_id, job_id)
        return self.capabilities()

    def unload(self):
        with self.guard:
            if self.active:
                self.active["canceled"] = True
                if self.active["process"]:
                    self.active["process"].terminate()
            self.model = None
            self.loaded_by = None
            self.epoch += 1

    def generate(self, project_id, job_id, observations, targets):
        if self.model is None:
            raise ValueError("Load the configured local checkpoint first")
        return self.worker("infer", project_id, job_id, observations=observations, targets=targets)


def decode_prediction(suggestion):
    data = base64.b64decode(suggestion["png"], validate=True)
    if len(data) > 50000 or hashlib.sha256(data).hexdigest() != suggestion["sha256"]:
        raise ValueError("Generated raster hash/size mismatch")
    return data
