import io
import json
import subprocess
import zipfile

import pytest
from ufoLib2 import Font

from test_workflow import fixture_image, png
from mashi import ocr
from mashi.exporting import glyph_name


def test_synthetic_fixture_survives_operations_and_requires_explicit_export(
    client, tmp_path, monkeypatch
):
    response = client.post("/api/projects?source=synthetic-fixture", content=png(fixture_image()))
    doc = response.json()
    base = f"/api/projects/{doc['id']}"
    assert doc["source_kind"] == "synthetic-fixture"
    assert all(r["provenance"] == "synthetic-fixture" for r in doc["regions"])
    parent = doc["regions"][0]
    doc = client.post(
        f"{base}/regions/{parent['id']}/split",
        json={"revision": parent["revision"], "axis": "x", "position": 80},
    ).json()
    children = doc["regions"][-2:]
    doc = client.post(
        f"{base}/merge",
        json={"ids": [r["id"] for r in children], "revisions": [r["revision"] for r in children]},
    ).json()
    merged = doc["regions"][-1]
    assert merged["provenance"] == "synthetic-fixture"
    doc = client.put(
        f"{base}/regions/{merged['id']}",
        json={
            "revision": merged["revision"],
            "box": merged["box"],
            "label": "ക",
            "confirmed": True,
        },
    ).json()
    merged = doc["regions"][-1]
    doc = client.post(
        f"{base}/regions/{merged['id']}/trace", json={"revision": merged["revision"]}
    ).json()
    assert client.get(base).json()["source_kind"] == "synthetic-fixture"
    assert doc["regions"][-1]["provenance"] == "synthetic-fixture"
    assert client.post(f"{base}/export/ufo").status_code == 400
    response = client.post(f"{base}/export/ufo?include_fixture=true")
    assert response.status_code == 200, response.text
    assert "SYNTHETIC" in response.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    report = json.loads(archive.read("coverage.json"))
    assert report["synthetic_test_export"] and report["observed"] == []
    assert report["synthetic_included"] == [merged["id"]]
    assert b"not actual handwriting" in archive.read("READ-ME.txt")
    assert b"synthetic-fixture" in archive.read("svg/u0D15.svg")
    archive.extractall(tmp_path / "fixture-font")
    font = Font.open(tmp_path / "fixture-font/Mashi-Synthetic.ufo")
    assert font.info.familyName == "Mashi Synthetic Fixture"
    assert font[glyph_name("ക")].lib["org.mashi.provenance"]["state"] == "synthetic-fixture"
    assert "synthetic-fixture" in client.get(f"{base}/regions/{merged['id']}/svg").text
    doc = client.post(
        f"{base}/regions", json={"box": [200, 20, 300, 160], "project_revision": doc["revision"]}
    ).json()
    assert doc["regions"][-1]["provenance"] == "synthetic-fixture"
    monkeypatch.setattr(
        ocr,
        "recognize",
        lambda p: [
            {"box": [200, 20, 300, 160], "raw_text": "മഷി", "granularity": "word", "confidence": 20}
        ],
    )
    doc = client.post(f"{base}/ocr", json={"revision": doc["revision"]}).json()
    assert doc["regions"][-1]["provenance"] == "synthetic-fixture"


def test_retrace_keeps_latest_manual_vector_and_metrics(client):
    doc = client.post("/api/projects", content=png(fixture_image())).json()
    base = f"/api/projects/{doc['id']}"
    region = doc["regions"][0]
    path = f"{base}/regions/{region['id']}"
    doc = client.post(path + "/trace", json={"revision": region["revision"]}).json()
    region = doc["regions"][0]
    edited = {
        "revision": region["revision"],
        "paths": ["M10 10L60 10L60 60L10 60Z"],
        "baseline": 70,
        "scale": 2.5,
        "advance": 321,
    }
    doc = client.put(path + "/vector", json=edited).json()
    before = doc["regions"][0]
    doc = client.post(
        path + "/trace", json={"revision": before["revision"], "threshold": 170}
    ).json()
    snapshot = [h["snapshot"] for h in doc["history"] if h["operation"] == "before-retrace"][-1]
    assert snapshot == before
    assert snapshot["vector"]["paths"] == edited["paths"]
    assert snapshot["vector"]["advance"] == 321
    assert snapshot["vector"]["baseline"] == 70
    assert snapshot["vector"]["scale"] == 2.5
    assert doc["regions"][0]["revision"] == before["revision"] + 1
    assert client.get(base).json()["history"][-2]["operation"] == "before-retrace"


def test_local_tessdata_and_word_parser(tmp_path, monkeypatch):
    folder = tmp_path / "language data"
    monkeypatch.setenv("MASHI_TESSDATA_DIR", str(folder))
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "/usr/bin/tesseract")
    seen = []

    def run(args, **kwargs):
        seen.append(args)
        if "--list-langs" in args:
            return subprocess.CompletedProcess(args, 0, "List of languages:\nmal\n", "")
        return subprocess.CompletedProcess(
            args,
            0,
            "level\tleft\ttop\twidth\theight\tconf\ttext\n5\t10\t20\t120\t40\t95\tക്ക\u200d\n",
            "",
        )

    monkeypatch.setattr(ocr.subprocess, "run", run)
    words = ocr.recognize(tmp_path / "input with spaces.png")
    assert words == [
        {
            "box": [10, 20, 130, 60],
            "raw_text": "ക്ക\u200d",
            "confidence": 95.0,
            "granularity": "word",
        }
    ]
    assert all(args[args.index("--tessdata-dir") + 1] == str(folder) for args in seen)


def test_missing_tsv_is_actionable(monkeypatch, tmp_path):
    monkeypatch.setattr(ocr, "capabilities", lambda: {"available": True})
    monkeypatch.setattr(ocr.shutil, "which", lambda name: "/usr/bin/tesseract")
    monkeypatch.setattr(
        ocr.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, "മഷി\n", ""),
    )
    with pytest.raises(ValueError, match="TSV word boxes"):
        ocr.recognize(tmp_path / "fixture.png")
