import hashlib
import io
import json
import subprocess
import zipfile

import pytest

from mashi import ocr, ocr_setup
from test_workflow import fixture_image, png
from fontTools.ttLib import TTFont
from fastapi.testclient import TestClient
from mashi.app import create_app


def fake_assets(monkeypatch):
    assets = {"mal.traineddata": b"synthetic model bytes", "LICENSE": b"synthetic notice"}
    monkeypatch.setattr(
        ocr_setup,
        "ASSETS",
        {name: hashlib.sha256(data).hexdigest() for name, data in assets.items()},
    )
    return assets


def test_status_is_read_only_and_distinguishes_engine_data_and_load_failure(tmp_path, monkeypatch):
    monkeypatch.delenv("MASHI_TESSDATA_DIR", raising=False)
    monkeypatch.setattr(
        ocr_setup.urllib.request, "urlopen", lambda *a, **k: pytest.fail("download")
    )
    monkeypatch.setattr(ocr.shutil, "which", lambda _: None)
    assert ocr.capabilities(tmp_path)["state"] == "missing-engine"
    assert not ocr.capabilities(tmp_path)["can_setup"]
    monkeypatch.setattr(ocr.shutil, "which", lambda _: "/trusted/tesseract")
    monkeypatch.setattr(
        ocr.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, b"eng\n", b"")
    )
    assert ocr.capabilities(tmp_path)["state"] == "missing-data"
    assert ocr.capabilities(tmp_path)["can_setup"]

    def corrupt(args, **kwargs):
        if "--list-langs" in args:
            return subprocess.CompletedProcess(args, 0, b"mal\n", b"")
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(ocr.subprocess, "run", corrupt)
    assert ocr.capabilities(tmp_path)["state"] == "data-error"
    monkeypatch.setattr(
        ocr.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, b"mal\n", b"")
    )
    assert ocr.capabilities(tmp_path)["available"]
    assert not list(tmp_path.iterdir())


def test_pinned_setup_stages_both_assets_and_is_idempotent(tmp_path, monkeypatch):
    assets = fake_assets(monkeypatch)
    calls = []

    def download(url, **kwargs):
        calls.append(url)
        assert url.startswith(ocr_setup.ROOT)
        return io.BytesIO(assets[url.rsplit("/", 1)[1]])

    monkeypatch.setattr(ocr_setup.urllib.request, "urlopen", download)
    output = tmp_path / "managed"
    record = ocr_setup.install_data(output)
    assert ocr_setup.verified(output)
    assert json.loads((output / "manifest.json").read_text()) == record
    assert (output / "LICENSE").read_bytes() == assets["LICENSE"]
    ocr_setup.install_data(output)
    assert len(calls) == 2
    assert not list(tmp_path.glob(".mal-setup-*"))


@pytest.mark.parametrize("failure", ["bad-hash", "oversized", "network"])
def test_failed_setup_publishes_nothing_and_preserves_legacy_data(tmp_path, monkeypatch, failure):
    assets = fake_assets(monkeypatch)
    legacy = tmp_path / "tessdata"
    legacy.mkdir()
    (legacy / "keep").write_bytes(b"existing user data")
    monkeypatch.setattr(ocr_setup, "MAX_ASSET", 64)

    def download(url, **kwargs):
        name = url.rsplit("/", 1)[1]
        if name == "LICENSE":
            if failure == "network":
                raise OSError("unavailable")
            return io.BytesIO(b"x" * (65 if failure == "oversized" else 1))
        return io.BytesIO(assets[name])

    monkeypatch.setattr(ocr_setup.urllib.request, "urlopen", download)
    with pytest.raises((OSError, ValueError)):
        ocr_setup.install_data(tmp_path / "new")
    assert not (tmp_path / "new").exists()
    assert (legacy / "keep").read_bytes() == b"existing user data"
    assert not list(tmp_path.glob(".mal-setup-*"))


def test_setup_rejects_existing_unverified_directory_and_symlink(tmp_path, monkeypatch):
    fake_assets(monkeypatch)
    folder = tmp_path / "user"
    folder.mkdir()
    (folder / "keep").write_bytes(b"preserve")
    link = tmp_path / "link"
    link.symlink_to(folder, target_is_directory=True)
    monkeypatch.setattr(
        ocr_setup.urllib.request, "urlopen", lambda *a, **k: pytest.fail("download")
    )
    for target in [folder, link]:
        with pytest.raises(ValueError, match="Existing recognition data"):
            ocr_setup.install_data(target)
    assert (folder / "keep").read_bytes() == b"preserve"


def test_api_setup_is_explicit_scoped_and_failure_is_retryable(client, monkeypatch, tmp_path):
    root = client.app.state.store.root
    calls = []

    def capability(data_root=None):
        assert data_root == root
        ready = ocr_setup.managed_directory(root).exists()
        return {
            "available": ready,
            "can_setup": not ready,
            "state": "ready" if ready else "missing-data",
            "reason": "Review words",
        }

    monkeypatch.setattr(ocr, "capabilities", capability)
    assert client.get("/api/ocr/status").json()["state"] == "missing-data"

    def install(target):
        calls.append(target)
        if len(calls) == 1:
            raise OSError("synthetic disk error with private path")
        target.mkdir(parents=True)

    monkeypatch.setattr("mashi.app.install_data", install)
    assert client.post("/api/ocr/setup", headers={"x-mashi-token": "bad"}).status_code == 403
    bad = client.post("/api/ocr/setup")
    assert bad.status_code == 400 and "private path" not in bad.text
    assert not client.get("/api/ocr/status").json()["available"]
    outside = tmp_path / "browser-chosen"
    assert client.post("/api/ocr/setup", json={"output": str(outside)}).json()["available"]
    assert not outside.exists() and calls == [ocr_setup.managed_directory(root)] * 2
    assert client.post("/api/ocr/setup").json()["available"]
    assert len(calls) == 2


def test_ocr_no_words_is_noop_and_late_results_cannot_overwrite_an_edit(client, monkeypatch):
    doc = client.post("/api/projects?source=synthetic-fixture", content=png(fixture_image())).json()
    base = f"/api/projects/{doc['id']}"
    monkeypatch.setattr(ocr, "recognize", lambda path, **kwargs: [])
    assert client.post(base + "/ocr", json={"revision": doc["revision"]}).json() == doc

    def stale(path, **kwargs):
        assert kwargs["data_root"] == client.app.state.store.root
        other = client.app.state.store.get(doc["id"])
        other["name"] = "Newer saved name"
        client.app.state.store.save(other)
        return [{"box": [10, 10, 30, 30], "raw_text": "ക", "confidence": 90, "granularity": "word"}]

    monkeypatch.setattr(ocr, "recognize", stale)
    assert client.post(base + "/ocr", json={"revision": doc["revision"]}).status_code == 409
    saved = client.get(base).json()
    assert saved["name"] == "Newer saved name"
    assert not any(r["source"] == "ocr-word" for r in saved["regions"])


@pytest.mark.parametrize(
    "row", ["5\t0\t0\t10\t10\tnan\tക", "5\t0\t0\t0\t10\t90\tക", "5\tx\t0\t10\t10\t90\tക"]
)
def test_bad_tsv_never_becomes_an_unhandled_error(tmp_path, monkeypatch, row):
    monkeypatch.setattr(ocr, "capabilities", lambda: {"available": True})
    monkeypatch.setattr(ocr.shutil, "which", lambda _: "/trusted/tesseract")
    monkeypatch.setattr(
        ocr.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a, 0, ("level\tleft\ttop\twidth\theight\tconf\ttext\n" + row + "\n").encode(), b""
        ),
    )
    with pytest.raises(ValueError, match="invalid crop data"):
        ocr.recognize(tmp_path / "fixture.png")


def test_image_alias_is_resolved_and_binary_diagnostics_are_never_decoded(tmp_path, monkeypatch):
    target = tmp_path / "actual"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    image = target / "printed.png"
    image.write_bytes(b"synthetic placeholder")
    monkeypatch.setattr(ocr, "capabilities", lambda: {"available": True})
    monkeypatch.setattr(ocr.shutil, "which", lambda _: "/trusted/tesseract")

    def run(args, **kwargs):
        assert args[1] == str(image.resolve())
        assert kwargs["stderr"] == subprocess.DEVNULL and "text" not in kwargs
        return subprocess.CompletedProcess(
            args,
            0,
            "level\tleft\ttop\twidth\theight\tconf\ttext\n5\t0\t0\t10\t10\t90\tന്‍\n".encode(),
            b"\x89PNG",
        )

    monkeypatch.setattr(ocr.subprocess, "run", run)
    assert ocr.recognize(alias / image.name)[0]["raw_text"] == "ന്‍"


def test_word_correction_reaches_actual_font_and_reopens_without_promoting_suggestions(
    client, monkeypatch, tmp_path
):
    doc = client.post("/api/projects?source=synthetic-fixture", content=png(fixture_image())).json()
    base = f"/api/projects/{doc['id']}"
    suggestion = {
        "box": [10, 10, 150, 160],
        "raw_text": "ക്ക‍",
        "confidence": 65,
        "granularity": "word",
    }
    monkeypatch.setattr(ocr, "recognize", lambda path, **kwargs: [suggestion])
    doc = client.post(base + "/ocr", json={"revision": doc["revision"]}).json()
    r = doc["regions"][-1]
    assert r["label"] == "" and not r["confirmed"] and r["vector"] is None
    assert r["suggestion"] == suggestion
    assert (
        client.post(
            base + "/proof/preflight?include_fixture=true",
            json={"revision": doc["revision"], "text": "ക"},
        ).json()["coverage"]["supported"]
        is False
    )
    path = base + "/regions/" + r["id"]
    doc = client.put(
        path,
        json={
            "revision": r["revision"],
            "box": [18, 18, 162, 162],
            "label": "ക",
            "confirmed": True,
        },
    ).json()
    r = doc["regions"][-1]
    doc = client.post(path + "/trace", json={"revision": r["revision"]}).json()
    assert doc["regions"][-1]["suggestion"]["raw_text"] == suggestion["raw_text"]
    proof = {"revision": doc["revision"], "text": "ക"}
    assert client.post(base + "/proof/preview?include_fixture=true", json=proof).json()["coverage"][
        "supported"
    ]
    assert client.post(base + "/export/ttf", json=proof).status_code == 400
    response = client.post(base + "/export/ttf?include_fixture=true", json=proof)
    assert response.status_code == 200, response.text
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    font = TTFont(
        io.BytesIO(archive.read(next(n for n in archive.namelist() if n.endswith(".ttf"))))
    )
    name = font.getBestCmap()[0x0D15]
    assert font["glyf"][name].numberOfContours == 2
    report = json.loads(archive.read("coverage.json"))
    assert report["observed"] == [] and report["synthetic_test_export"]
    assert not any(n.endswith((".png", ".jpg", ".webp", ".bin")) for n in archive.namelist())
    reopened = create_app(client.app.state.store.root, testing=True)
    with TestClient(reopened) as c:
        saved = c.get(base).json()["regions"][-1]
        assert saved["label"] == "ക" and saved["confirmed"] and saved["vector"]
        assert saved["suggestion"]["raw_text"] == suggestion["raw_text"]
