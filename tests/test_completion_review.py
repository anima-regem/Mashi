"""Original synthetic contract fixtures; no checkpoint/corpus is bundled or trained here."""

import hashlib
import io
import json
import plistlib
import threading
import subprocess
import struct
import uuid
import zipfile

import numpy as np
import pytest
from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont
from scipy.ndimage import distance_transform_edt

from mashi.app import create_app
from mashi.ml_capture import aligned_reference
from mashi.ml_capture import pixel_boundaries
from mashi.ml_engine import checkpoint
from mashi.ml_service import CompletionService
from test_workflow import fixture_image, png


def fixture_checkpoint(path, version=3, **overrides):
    labels = np.array(["ക", "ഖ", "മ", "ന്\u200d"])
    masks = np.zeros((4, 64, 96), bool)
    masks[:, 24:45, 35:58] = True
    masks[1, 29:39, 41:52] = False
    mean = np.stack(
        [
            np.clip((distance_transform_edt(m) - distance_transform_edt(~m)) / 6, -1, 1).astype(
                np.float32
            )
            for m in masks
        ]
    )
    config = {"method": "pca", "rank": 1, "ridge": 0.001, "band": False, "blend": 1.0}
    metadata = {"inference_config": config}
    arrays = {
        "format_version": np.array(version),
        "labels": labels,
        "mean": mean,
        "basis": np.zeros((1, *mean.shape), np.float32),
    }
    if version == 3:
        metadata.update(
            profile="pca-inference-v1",
            capabilities={
                "pca_inference": True,
                "mean_inference": True,
                "template_baselines": False,
                "nearest_template_diagnostic": False,
            },
        )
    else:
        arrays.update(
            templates=np.stack([mean]), template_ids=np.array(["original-synthetic-fixture"])
        )
    arrays["metadata"] = np.array(json.dumps(metadata))
    arrays.update(overrides)
    np.savez_compressed(path, **arrays)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def ml_client(tmp_path, monkeypatch):
    path = tmp_path / "synthetic-contract.npz"
    digest = fixture_checkpoint(path)
    monkeypatch.setenv("MASHI_COMPLETION_CHECKPOINT", str(path))
    monkeypatch.setenv("MASHI_COMPLETION_SHA256", digest)
    with TestClient(create_app(tmp_path / "data", testing=True)) as client:
        client.headers["x-mashi-token"] = client.get("/api/session").json()["token"]
        yield client


def ready(client):
    doc = client.post("/api/projects?source=synthetic-fixture", content=png(fixture_image())).json()
    base = f"/api/projects/{doc['id']}"
    r = doc["regions"][0]
    doc = client.put(
        f"{base}/regions/{r['id']}",
        json={"revision": r["revision"], "box": r["box"], "label": "ക", "confirmed": True},
    ).json()
    r = doc["regions"][0]
    doc = client.post(f"{base}/regions/{r['id']}/trace", json={"revision": r["revision"]}).json()
    r = doc["regions"][0]
    return doc, base, r


def generation(client, doc, base, r, targets=None):
    load = client.post(
        base + "/completion/load", json={"revision": doc["revision"], "job_id": str(uuid.uuid4())}
    )
    assert load.status_code == 200, load.text
    refs = client.post(
        base + "/completion/references", json={"revision": doc["revision"], "ids": [r["id"]]}
    ).json()["references"]
    return {
        "revision": doc["revision"],
        "job_id": str(uuid.uuid4()),
        "ids": [r["id"]],
        "targets": targets or ["ഖ"],
        "reference_hashes": {v["id"]: v["sha256"] for v in refs},
        "alignment_confirmed": True,
    }


@pytest.mark.parametrize("version", [2, 3])
def test_safe_profiles_and_no_template_reads(tmp_path, monkeypatch, version):
    path = tmp_path / "model.npz"
    digest = fixture_checkpoint(path, version)
    original = np.load
    accessed = []

    class Proxy:
        def __init__(self, real):
            self.real = real
            self.files = real.files

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.real.close()

        def __getitem__(self, key):
            accessed.append(key)
            assert key not in {"templates", "template_ids"}
            return self.real[key]

    monkeypatch.setattr(np, "load", lambda *a, **k: Proxy(original(*a, **k)))
    model = checkpoint(path, digest)
    assert model["format_version"] == version
    assert model["capabilities"]["nearest_template_diagnostic"] is (version == 2)
    assert "basis" in accessed


def test_checkpoint_rejects_pickle_corruption_and_unbounded_shapes(tmp_path, monkeypatch):
    path = tmp_path / "bad.npz"
    digest = fixture_checkpoint(path, labels=np.array([object()], dtype=object))
    with pytest.raises(ValueError, match="Unsafe"):
        checkpoint(path, digest)
    digest = fixture_checkpoint(path, basis=np.full((1, 4, 64, 96), np.nan, np.float32))
    with pytest.raises(ValueError, match="nonfinite"):
        checkpoint(path, digest)
    digest = fixture_checkpoint(path)
    with pytest.raises(ValueError, match="SHA-256"):
        checkpoint(path, "0" * 64)
    monkeypatch.setattr("mashi.ml_engine.MAX_EXPANDED", 1)
    with pytest.raises(ValueError, match="512 MiB"):
        checkpoint(path, digest)
    monkeypatch.setattr("mashi.ml_engine.MAX_FILE", 1)
    with pytest.raises(ValueError, match="96 MiB"):
        checkpoint(path, digest)


def test_checkpoint_rejects_paths_capability_lies_and_template_methods(tmp_path):
    path = tmp_path / "bad.npz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../../outside.npy", b"no")
    with pytest.raises(ValueError, match="unexpected|members"):
        checkpoint(path, hashlib.sha256(path.read_bytes()).hexdigest())
    metadata = {
        "profile": "pca-inference-v1",
        "capabilities": {},
        "inference_config": {"method": "nearest-template"},
    }
    digest = fixture_checkpoint(path, metadata=np.array(json.dumps(metadata)))
    with pytest.raises(ValueError, match="capability"):
        checkpoint(path, digest)
    metadata = {"inference_config": {"method": "nearest-template", "rank": 1}}
    digest = fixture_checkpoint(path, 2, metadata=np.array(json.dumps(metadata)))
    with pytest.raises(ValueError, match="Template"):
        checkpoint(path, digest)


def test_default_off_and_browser_cannot_supply_a_path(client, ml_client):
    assert not client.get("/api/completion/capabilities").json()["loaded"]
    doc, base, _ = ready(ml_client)
    result = ml_client.post(
        base + "/completion/load",
        json={
            "revision": doc["revision"],
            "job_id": str(uuid.uuid4()),
            "checkpoint": "/etc/passwd",
        },
    )
    assert result.status_code == 422
    assert not ml_client.get("/api/completion/capabilities").json()["loaded"]


def test_missing_optional_dependency_does_not_block_capture(ml_client, monkeypatch):
    import importlib.util

    original = importlib.util.find_spec
    monkeypatch.setattr(
        importlib.util,
        "find_spec",
        lambda name, *args: None if name == "scipy" else original(name, *args),
    )
    assert not ml_client.get("/api/completion/capabilities").json()["available"]
    doc, base, _ = ready(ml_client)
    assert (
        ml_client.post(
            base + "/completion/load",
            json={"revision": doc["revision"], "job_id": str(uuid.uuid4())},
        ).status_code
        == 400
    )
    assert ml_client.post(base + "/export/ufo?include_fixture=true").status_code == 200


def test_alignment_and_missing_target_gates(ml_client):
    doc, base, r = ready(ml_client)
    body = generation(ml_client, doc, base, r)
    before = ml_client.get(base).json()
    for changed in [
        {"alignment_confirmed": False},
        {"reference_hashes": {}},
        {"targets": ["ക"]},
        {"targets": ["സ്ത്ര"]},
        {"targets": ["ഖ", "ഖ"]},
    ]:
        assert (
            ml_client.post(base + "/completion/generate", json={**body, **changed}).status_code
            == 400
        )
    assert ml_client.get(base).json() == before
    vector = {**r, "vector": dict(doc["regions"][0]["vector"])}
    vector["vector"]["baseline"] = -100000
    with pytest.raises(ValueError, match="baseline/scale"):
        aligned_reference(vector)


def test_review_edit_reject_and_default_exclusion(ml_client):
    doc, base, r = ready(ml_client)
    result = ml_client.post(base + "/completion/generate", json=generation(ml_client, doc, base, r))
    assert result.status_code == 200, result.text
    doc = result.json()
    s = doc["completion_suggestions"][0]
    assert (
        s["provenance"] == "model-generated"
        and s["review_state"] == "pending"
        and not s["confirmed"]
    )
    assert s["generation"]["observations"][0]["provenance"] == "synthetic-fixture"
    accepted = ml_client.post(
        f"{base}/completion/suggestions/{s['id']}/review",
        json={
            "revision": doc["revision"],
            "suggestion_revision": s["revision"],
            "state": "accepted",
        },
    )
    assert accepted.status_code == 200, accepted.text
    doc = accepted.json()
    s = doc["completion_suggestions"][0]
    assert s["provenance"] == "model-generated" and s["confirmed"]
    coverage = ml_client.post(
        base + "/proof/preflight?include_fixture=true",
        json={"revision": doc["revision"], "text": "ഖ"},
    ).json()
    assert not coverage["coverage"]["supported"]
    # Unclassified fixture hashes do not acquire a licence merely by acceptance.
    assert (
        ml_client.post(
            base + "/export/ttf?include_fixture=true&include_generated=true",
            json={"revision": doc["revision"], "text": "ഖ"},
        ).status_code
        == 400
    )
    edited = ml_client.put(
        f"{base}/completion/suggestions/{s['id']}/vector",
        json={
            "project_revision": doc["revision"],
            "revision": s["revision"],
            **{k: s["vector"][k] for k in ["paths", "baseline", "scale", "advance"]},
        },
    )
    assert edited.status_code == 200, edited.text
    doc = edited.json()
    s = doc["completion_suggestions"][0]
    assert (
        s["review_state"] == "pending"
        and not s["confirmed"]
        and s["provenance"] == "model-generated"
    )
    rejected = ml_client.post(
        f"{base}/completion/suggestions/{s['id']}/review",
        json={
            "revision": doc["revision"],
            "suggestion_revision": s["revision"],
            "state": "rejected",
        },
    ).json()
    assert rejected["completion_suggestions"][0]["review_state"] == "rejected"
    ml_client.post("/api/completion/unload")
    assert not ml_client.get("/api/completion/capabilities").json()["loaded"]
    assert ml_client.post(base + "/export/ufo?include_fixture=true").status_code == 200


def test_generated_font_notices_and_glyph_provenance(ml_client, monkeypatch):
    import mashi.ml_service as service

    original = service.source_terms

    # Explicit unit-only stand-in for the production hash-bound source registry.
    def fixture_terms(digest):
        return original("0165690674d47818bd66055cf66f7b8861bdbb557f964bea56154b33180ea045")

    monkeypatch.setattr(service, "source_terms", fixture_terms)
    monkeypatch.setattr("mashi.exporting.source_terms", fixture_terms)
    doc, base, r = ready(ml_client)
    doc = ml_client.post(
        base + "/completion/generate", json=generation(ml_client, doc, base, r)
    ).json()
    s = doc["completion_suggestions"][0]
    doc = ml_client.post(
        f"{base}/completion/suggestions/{s['id']}/review",
        json={
            "revision": doc["revision"],
            "suggestion_revision": s["revision"],
            "state": "accepted",
        },
    ).json()
    body = {"revision": doc["revision"], "text": "ഖ"}
    output = ml_client.post(
        base + "/export/ttf?include_fixture=true&include_generated=true", json=body
    )
    assert output.status_code == 200, output.text
    with zipfile.ZipFile(io.BytesIO(output.content)) as archive:
        report = json.loads(archive.read("coverage.json"))
        assert report["generated_font"] and report["included_generated"] == [s["id"]]
        assert report["observed"] == [] and s["id"] not in report["synthetic_included"]
        assert "OFL-1.1" in archive.read("GENERATED-PROVENANCE.json").decode()
        assert archive.read("FONT-LICENSES/OFL.txt")
        assert b"SYNTHETIC TEST INPUT" in archive.read("READ-ME.txt")
        tt = TTFont(io.BytesIO(archive.read("Mashi-Synthetic-Generated.ttf")))
        assert "Generated" in tt["name"].getDebugName(1)
        assert "OPEN FONT LICENSE" in tt["name"].getDebugName(13)
        directory = "Mashi-Synthetic-Generated.ufo/glyphs/"
        contents = plistlib.loads(archive.read(directory + "contents.plist"))
        glyph = archive.read(directory + contents["u0D16"]).decode()
        assert "model-generated" in glyph and "notObservedInPhoto" in glyph
        from fontTools.pens.pointInsidePen import PointInsidePen

        glyphs = tt.getGlyphSet()
        for x, expected in [(37, True), (46, False)]:
            pen = PointInsidePen(glyphs, ((x - s["box"][0]) * 31.25 + 50, (45 - 34) * 31.25))
            glyphs["u0D16"].draw(pen)
            assert pen.getResult() is expected
    assert (
        ml_client.post(
            base + "/export/ttf?include_fixture=true&include_generated=true",
            json={**body, "options": {"family_name": "Rachana"}},
        ).status_code
        == 400
    )

    ref = doc["regions"][0]
    changed = ml_client.put(
        f"{base}/regions/{ref['id']}/vector",
        json={
            "revision": ref["revision"],
            **{k: ref["vector"][k] for k in ["paths", "scale", "advance"]},
            "baseline": ref["vector"]["baseline"] + 1,
        },
    ).json()
    stale = ml_client.post(
        base + "/export/ufo?include_fixture=true&include_generated=true",
        json={"revision": changed["revision"], "text": "ഖ"},
    )
    assert stale.status_code == 400 and "references changed" in stale.text.lower()
    assert ml_client.post(base + "/export/ufo?include_fixture=true").status_code == 200


def test_stale_generation_and_changed_references_are_rejected(ml_client, monkeypatch):
    doc, base, r = ready(ml_client)
    body = generation(ml_client, doc, base, r)
    service = ml_client.app.state.completion
    original = service.generate

    def racing(*args, **kwargs):
        result = original(*args, **kwargs)
        saved = ml_client.app.state.store.get(doc["id"])
        ml_client.app.state.store.save(saved)
        return result

    monkeypatch.setattr(service, "generate", racing)
    assert ml_client.post(base + "/completion/generate", json=body).status_code == 409
    current = ml_client.get(base).json()
    assert not current.get("completion_suggestions")
    assert ml_client.post(base + "/completion/generate", json=body).status_code == 409


def test_untraceable_prediction_cannot_be_accepted_and_capture_still_exports(
    ml_client, monkeypatch
):
    doc, base, r = ready(ml_client)
    body = generation(ml_client, doc, base, r)

    def failed_trace(*args):
        raise ValueError("Synthetic tracer failure")

    monkeypatch.setattr("mashi.app.trace", failed_trace)
    monkeypatch.setattr("mashi.app.pixel_boundaries", failed_trace)
    doc = ml_client.post(base + "/completion/generate", json=body).json()
    item = doc["completion_suggestions"][0]
    assert item["trace_error"] == "Synthetic tracer failure" and item["vector"] is None
    rejected = ml_client.post(
        f"{base}/completion/suggestions/{item['id']}/review",
        json={
            "revision": doc["revision"],
            "suggestion_revision": item["revision"],
            "state": "accepted",
        },
    )
    assert rejected.status_code == 400
    assert ml_client.post(base + "/export/ufo?include_fixture=true").status_code == 200


def test_pixel_fallback_keeps_every_ink_pixel_and_counters():
    from PIL import Image
    from fontTools.pens.pointInsidePen import PointInsidePen
    from fontTools.svgLib.path import parse_path

    mask = np.zeros((12, 12), bool)
    mask[2:10, 2:10] = True
    mask[4:8, 4:8] = False
    mask[0, 0] = True
    mask[1, 1] = True
    outline = pixel_boundaries(Image.fromarray(np.where(mask, 0, 255).astype(np.uint8)))
    for y in range(12):
        for x in range(12):
            pen = PointInsidePen(None, (x + 0.5, y + 0.5))
            parse_path(outline["paths"][0], pen)
            assert pen.getResult() == bool(mask[y, x])


def test_cancel_terminates_only_its_worker_and_canceled_load_stays_off(tmp_path, monkeypatch):
    path = tmp_path / "model.npz"
    digest = fixture_checkpoint(path)
    service = CompletionService(path, digest)
    started, stop = threading.Event(), threading.Event()

    class Process:
        returncode = -15
        terminated = False

        def __init__(self, *args, **kwargs):
            started.set()

        def terminate(self):
            self.terminated = True
            stop.set()

        def communicate(self, *args, **kwargs):
            stop.wait(5)
            return "{}", ""

    monkeypatch.setattr("mashi.ml_service.subprocess.Popen", Process)
    errors = []

    def run():
        try:
            service.load("project", "job")
        except ValueError as error:
            errors.append(str(error))

    thread = threading.Thread(target=run)
    thread.start()
    assert started.wait(3)
    service.cancel("different-project", "job")
    assert not stop.is_set()
    service.cancel("project", "job")
    thread.join(5)
    assert not thread.is_alive() and "canceled" in errors[0]
    assert service.model is None


def test_actual_oversized_sparse_checkpoint_and_duplicate_members_are_rejected(tmp_path):
    path = tmp_path / "oversized.npz"
    with path.open("wb") as stream:
        stream.truncate(96 * 1024 * 1024 + 1)
    with pytest.raises(ValueError, match="96 MiB"):
        checkpoint(path, "0" * 64)
    path = tmp_path / "duplicates.npz"
    fixture_checkpoint(path)
    with zipfile.ZipFile(path, "a") as archive:
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("labels.npy", b"not another array")
    with pytest.raises(ValueError, match="duplicate|members"):
        checkpoint(path, hashlib.sha256(path.read_bytes()).hexdigest())


def test_worker_timeout_clears_slot_and_kills_only_the_owned_process(tmp_path, monkeypatch):
    path = tmp_path / "model.npz"
    digest = fixture_checkpoint(path)
    service = CompletionService(path, digest)
    killed = []

    class Process:
        def __init__(self, *args, **kwargs):
            pass

        def communicate(self, *args, **kwargs):
            if "timeout" in kwargs:
                raise subprocess.TimeoutExpired("owned-worker", 45)
            return "{}", ""

        def kill(self):
            killed.append(True)

    monkeypatch.setattr("mashi.ml_service.subprocess.Popen", Process)
    with pytest.raises(ValueError, match="45 seconds"):
        service.worker("inspect", "project", "job")
    assert killed == [True] and service.active is None and service.model is None


def test_forged_directory_count_is_rejected_before_zip_objects_are_allocated(tmp_path, monkeypatch):
    path = tmp_path / "forged.npz"
    fixture_checkpoint(path)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("extra.npy", b"not an array")
    payload = bytearray(path.read_bytes())
    end = payload.rfind(b"PK\x05\x06")
    struct.pack_into("<HH", payload, end + 8, 5, 5)
    path.write_bytes(payload)

    def forbidden(*args, **kwargs):
        raise AssertionError("ZipInfo allocation must follow the bounded directory check")

    monkeypatch.setattr("mashi.ml_engine.zipfile.ZipFile", forbidden)
    with pytest.raises(ValueError, match="count mismatch"):
        checkpoint(path, hashlib.sha256(payload).hexdigest())
