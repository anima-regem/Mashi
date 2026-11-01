"""Synthetic font machinery and multi-tab revision checks, not handwriting accuracy."""

import io
import json
import zipfile
from uuid import uuid4

from fontTools.ttLib import TTFont
from fontTools.svgLib.path import parse_path
from fontTools.pens.pointInsidePen import PointInsidePen

from mashi import app as app_module
from mashi.proofing import PreviewCache
from mashi.font_metrics import TypographyOptions
from test_typography import synthetic_typography
from test_workflow import fixture_image, png


def stored_fixture(client, labels=None):
    doc = synthetic_typography(labels)
    doc.update(id=uuid4().hex, revision=1)
    client.app.state.store.create(doc)
    return doc, f"/api/projects/{doc['id']}"


def test_exact_preflight_and_provenance(client):
    doc, base = stored_fixture(client, ["ക", "്", "ക്ക"])
    exact = "ക്ക\nന്\u200d കൊ"
    body = {"revision": 1, "text": exact}
    result = client.post(base + "/proof/preflight", json=body).json()
    assert result["coverage"]["text"] == exact
    assert not result["coverage"]["supported"]
    result = client.post(base + "/proof/preflight?include_fixture=true", json=body).json()
    assert result["coverage"]["text"] == exact
    assert set(["ന", "്", "ൻ", "െ", "ാ"]) - {"്"} <= set(result["coverage"]["required_samples"])
    assert result["revision"] == 1 and result["coverage"]["synthetic_test_export"]
    assert client.app.state.store.get(doc["id"]) == doc
    long_text = "x" * 150
    limited = client.post(base + "/proof/preflight", json={"revision": 1, "text": long_text}).json()
    assert limited["coverage"]["issues_total"] == 150
    assert len(limited["coverage"]["issues"]) == 100 and limited["coverage"]["issues_truncated"]
    assert (
        client.post(base + "/proof/preflight", json={"revision": 1, "text": "\n" * 33}).status_code
        == 422
    )


def test_real_preview_cache_invalidation_and_required_export(client, monkeypatch):
    doc, base = stored_fixture(client, ["ക", "്", "ക്ക", "െ", "ാ"])
    original, calls = app_module.preview_project, []

    def tracked(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(app_module, "preview_project", tracked)
    exact = "കൊ ക്ക\nക"
    body = {"revision": 1, "text": exact, "options": {"space_advance": 333, "line_gap": 120}}
    endpoint = base + "/proof/preview?include_fixture=true"
    first = client.post(endpoint, json=body)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["coverage"]["supported"] and not result["preview"]["has_notdef"]
    assert result["preview"]["text"] == exact and result["drawing"]["paths"]["u0D15_0D4D_0D15"]
    assert result["drawing"]["lines"][0]["glyphs"][0]["name"] == "u0D46"
    assert result["drawing"]["line_advance"] == 1520
    assert result["drawing"]["lines"][1]["baseline_offset"] == 1520
    assert not result["cache"]["hit"]
    assert client.post(endpoint, json=body).json()["cache"]["hit"] and len(calls) == 1
    changed = {**body, "options": {"space_advance": 444}}
    assert not client.post(endpoint, json=changed).json()["cache"]["hit"] and len(calls) == 2
    exported = client.post(base + "/export/ttf?include_fixture=true", json=body)
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as bundle:
        report = json.loads(bundle.read("coverage.json"))
        assert report["required_text"]["text"] == exact
        assert report["required_preview"]["text"] == exact
        assert report["typography_options"]["space_advance"] == 333
        assert report["font_family"] == "Mashi Synthetic Fixture"
        font = TTFont(io.BytesIO(bundle.read("Mashi-Synthetic.ttf")))
        assert font["hmtx"].metrics["space"][0] == 333
    client.app.state.store.save(doc)
    assert client.post(endpoint, json=body).status_code == 409
    assert client.post(base + "/export/ttf?include_fixture=true", json=body).status_code == 409
    updated = {**body, "revision": 2}
    assert not client.post(endpoint, json=updated).json()["cache"]["hit"] and len(calls) == 3
    assert all(key[1] == 2 for key in client.app.state.previews.entries)
    unsupported = {**updated, "text": "സ്ത്ര"}
    assert (
        client.post(base + "/export/ttf?include_fixture=true", json=unsupported).status_code == 400
    )


def test_stale_result_after_compile_is_rejected(client, monkeypatch):
    doc, base = stored_fixture(client, ["ക"])
    original = app_module.preview_project

    def racing(*args, **kwargs):
        result = original(*args, **kwargs)
        client.app.state.store.save(doc)
        return result

    monkeypatch.setattr(app_module, "preview_project", racing)
    result = client.post(
        base + "/proof/preview?include_fixture=true", json={"revision": 1, "text": "ക"}
    )
    assert result.status_code == 409


def test_positioned_proof_paths_keep_the_traced_counter(client):
    doc = client.post("/api/projects?source=synthetic-fixture", content=png(fixture_image())).json()
    base = f"/api/projects/{doc['id']}"
    crop = doc["regions"][0]
    doc = client.put(
        f"{base}/regions/{crop['id']}",
        json={"revision": crop["revision"], "box": crop["box"], "label": "ക", "confirmed": True},
    ).json()
    crop = doc["regions"][0]
    doc = client.post(
        f"{base}/regions/{crop['id']}/trace", json={"revision": crop["revision"]}
    ).json()
    vector = doc["regions"][0]["vector"]
    result = client.post(
        base + "/proof/preview?include_fixture=true",
        json={"revision": doc["revision"], "text": "ക"},
    ).json()
    path = result["drawing"]["paths"]["u0D15"]
    for original, expected in [((80, 80), False), ((80, 25), True)]:
        x, y = original[0] - crop["box"][0], original[1] - crop["box"][1]
        pen = PointInsidePen(
            None, (x * vector["scale"] + 50, (vector["baseline"] - y) * vector["scale"])
        )
        parse_path(path, pen)
        assert pen.getResult() is expected


def test_export_refuses_a_revision_changed_during_compilation(client, monkeypatch):
    doc, base = stored_fixture(client, ["ക"])
    original = app_module.export_bundle

    def racing(*args, **kwargs):
        data = original(*args, **kwargs)
        client.app.state.store.save(doc)
        return data

    monkeypatch.setattr(app_module, "export_bundle", racing)
    response = client.post(
        base + "/export/ttf?include_fixture=true", json={"revision": 1, "text": "ക"}
    )
    assert response.status_code == 409 and response.headers["content-type"] == "application/json"


def test_cache_failure_retry_and_bound():
    cache = PreviewCache(capacity=1)
    doc = {"id": "fixture", "revision": 1}

    def fail():
        raise ValueError("compiler test failure")

    import pytest

    with pytest.raises(ValueError):
        cache.get(doc, "ക", TypographyOptions(), False, fail)
    assert not cache.entries

    def result():
        return {"coverage": {"issues": []}, "preview": {"diagnostics": []}}

    cache.get(doc, "ക", TypographyOptions(), False, result)
    cache.get(doc, "ഖ", TypographyOptions(), False, result)
    assert len(cache.entries) == 1
    cache.get(doc, "ഖ", TypographyOptions(), True, result)
    assert next(iter(cache.entries))[3] is True


def test_generated_ink_cannot_satisfy_proof(client):
    doc, base = stored_fixture(client, ["ക", "ഖ"])
    doc["regions"][1]["provenance"] = "model-generated"
    client.app.state.store.save(doc)
    body = {"revision": 2, "text": "ഖ"}
    result = client.post(base + "/proof/preview?include_fixture=true", json=body).json()
    assert not result["coverage"]["supported"] and result["preview"]["has_notdef"]
    assert "u0D16" not in result["drawing"]["paths"]
    assert client.post(base + "/export/ttf?include_fixture=true", json=body).status_code == 400


def test_stale_image_crop_and_ocr_are_rejected_without_touching_new_pixels(client, monkeypatch):
    # Tab A holds old metadata; tab B rotates the same saved page.
    old = client.post("/api/projects", content=png(fixture_image())).json()
    base = f"/api/projects/{old['id']}"
    fresh = client.post(
        base + "/preparation", json={"revision": old["revision"], "rotation": 12}
    ).json()
    assert fresh["image"]["canonical_sha256"] != old["image"]["canonical_sha256"]
    called = []
    monkeypatch.setattr("mashi.ocr.recognize", lambda path: called.append(path) or [])
    stale_crop = client.post(
        base + "/regions", json={"box": [10, 10, 80, 80], "project_revision": old["revision"]}
    )
    assert stale_crop.status_code == 409
    assert client.post(base + "/regions", json={"box": [10, 10, 80, 80]}).status_code == 422
    assert client.post(base + "/ocr", json={"revision": old["revision"]}).status_code == 409
    assert not called and client.get(base).json() == fresh
    assert (
        client.get(base + "/image?expected_sha256=" + old["image"]["canonical_sha256"]).status_code
        == 409
    )
    assert (
        client.get(
            base + "/image?expected_sha256=" + fresh["image"]["canonical_sha256"]
        ).status_code
        == 200
    )
    created = client.post(
        base + "/regions", json={"box": [10, 10, 80, 80], "project_revision": fresh["revision"]}
    ).json()
    region = created["regions"][-1]
    assert not region["label"] and not region["confirmed"] and region["source_polygon"]
