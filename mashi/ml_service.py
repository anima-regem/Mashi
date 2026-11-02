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
    def __init__(self, path=None, digest=None, *, data_root=None):
        self.configuration_error = False
        self.configuration_source = "environment"
        if (
            path is None
            and digest is None
            and not (
                os.environ.get("MASHI_COMPLETION_CHECKPOINT")
                or os.environ.get("MASHI_COMPLETION_SHA256")
            )
            and data_root is not None
        ):
            from .completion_setup import read_profile

            self.configuration_source = "local-profile"
            try:
                profile = read_profile(data_root)
                if profile and profile["enabled"]:
                    path, digest = profile["checkpoint"], profile["sha256"]
            except (ValueError, OSError, RuntimeError):
                self.configuration_error = True
        self.path = None
        try:
            candidate = path or os.environ.get("MASHI_COMPLETION_CHECKPOINT")
            if candidate:
                if len(str(candidate)) > 4096 or "\0" in str(candidate):
                    raise ValueError("Invalid checkpoint path")
                self.path = Path(candidate).expanduser().resolve()
        except (ValueError, OSError, RuntimeError):
            self.configuration_error = True
        self.digest = digest or os.environ.get("MASHI_COMPLETION_SHA256", "")
        self.model = None
        self.guard = threading.Lock()
        self.active = None
        self.canceled = {}
        self.loaded_by = None
        self.epoch = 0
        self.last_failure = None

    def capabilities(self):
        configured = bool(self.path and re.fullmatch("[a-f0-9]{64}", self.digest))
        state, available = "unconfigured", False
        if self.configuration_error or ((self.path or self.digest) and not configured):
            state = "configuration-error"
        elif configured:
            try:
                valid = self.path.suffix == ".npz" and self.path.is_file()
                size = self.path.stat().st_size if valid else 0
                state = (
                    "checkpoint-missing"
                    if not valid
                    else "checkpoint-invalid"
                    if not 0 < size <= 96 * 1024 * 1024
                    else "off"
                )
            except OSError:
                state = "checkpoint-unavailable"
            if state == "off":
                try:
                    available = importlib.util.find_spec("scipy") is not None
                except (ImportError, ValueError):
                    available = False
                state = (
                    ("loaded" if self.model is not None else self.last_failure or "off")
                    if available
                    else "runtime-missing"
                )
        reasons = {
            "unconfigured": "No local model is selected. You can capture missing forms manually.",
            "configuration-error": "Local model settings need attention. Capture missing forms manually or review model setup.",
            "checkpoint-missing": "The selected model file is missing. Choose it again in model setup.",
            "checkpoint-invalid": "The selected model file is unsupported. Review model setup.",
            "checkpoint-unavailable": "The selected model could not be read. Review model setup or capture manually.",
            "runtime-missing": "Completion is unavailable in this installation. You can capture missing forms manually.",
            "load-error": "The model could not load. Check model setup and try again; capture still works.",
            "off": "Suggestions are off. Load the model to continue.",
            "loaded": "Choose reference forms and review every generated suggestion.",
        }
        return {
            "configured": configured,
            "available": available,
            "loaded": available and self.model is not None,
            "model": self.model if available else None,
            "state": state,
            "runtime_checked": available and self.model is not None,
            "configuration_source": self.configuration_source if configured else None,
            "profile": "configured-local-checkpoint" if configured else None,
            "filename": self.path.name if configured else None,
            "reason": reasons[state],
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
                "Suggestions could not be generated. Try again or capture the missing forms."
            ) from error
        finally:
            with self.guard:
                self.active = None

    def load(self, project_id, job_id):
        epoch = self.epoch
        try:
            result = self.worker("inspect", project_id, job_id)
        except ValueError as error:
            with self.guard:
                canceled = epoch != self.epoch or (project_id, job_id) in self.canceled
                if not canceled and self.active is None:
                    self.model = None
                    self.last_failure = "load-error"
            if canceled:
                raise ValueError("Checkpoint load canceled") from None
            raise ValueError(
                "The local model could not load. Review model setup and try again; capture still works."
            ) from error
        with self.guard:
            if epoch != self.epoch or (project_id, job_id) in self.canceled:
                raise ValueError("Checkpoint load canceled")
            self.model = result["model"]
            self.last_failure = None
            self.loaded_by = (project_id, job_id)
        return self.capabilities()

    def unload(self):
        with self.guard:
            if self.active:
                self.active["canceled"] = True
                if self.active["process"]:
                    self.active["process"].terminate()
            self.model = None
            self.last_failure = None
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
