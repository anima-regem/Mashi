import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from fastapi.testclient import TestClient

from mashi.app import create_app
from mashi.completion_setup import configure, disable, profile_path, read_profile
from mashi.ml_service import CompletionService
from test_completion_review import fixture_checkpoint, ready


@pytest.fixture(autouse=True)
def no_environment_profile(monkeypatch):
    monkeypatch.delenv("MASHI_COMPLETION_CHECKPOINT", raising=False)
    monkeypatch.delenv("MASHI_COMPLETION_SHA256", raising=False)


@pytest.mark.parametrize("version", [2, 3])
def test_explicit_setup_preserves_external_weights_and_restart_is_off(tmp_path, version):
    path = tmp_path / "external model.npz"
    digest = fixture_checkpoint(path, version)
    root = tmp_path / "projects"
    result = configure(root, path, digest)
    assert result["state"] == "off" and result["sequence_count"] == 4
    assert result["format_version"] == version and not result["checkpoint_source_known"]
    assert "unresolved" in result["checkpoint_distribution"]
    saved = read_profile(root)
    assert saved["checkpoint"] == str(path.resolve()) and saved["sha256"] == digest
    assert profile_path(root).stat().st_mode & 0o777 == 0o600
    assert [p.name for p in root.rglob("*") if p.is_file()] == ["profile.json"]
    service = CompletionService(data_root=root)
    assert service.capabilities()["state"] == "off"
    assert not service.capabilities()["loaded"]
    assert service.capabilities()["configuration_source"] == "local-profile"
    assert service.load("test-setup", "explicit-load")["loaded"]
    service.unload()
    assert service.capabilities()["state"] == "off"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    disable(root)
    assert CompletionService(data_root=root).capabilities()["state"] == "unconfigured"
    assert path.is_file(), "Disabling must not delete the user's external model"


def test_setup_failure_and_failed_publication_keep_prior_profile_exactly(tmp_path, monkeypatch):
    path = tmp_path / "model.npz"
    digest = fixture_checkpoint(path)
    root = tmp_path / "data"
    configure(root, path, digest)
    before = profile_path(root).read_bytes()
    with pytest.raises(ValueError, match="could not load"):
        configure(root, path, "0" * 64)
    assert profile_path(root).read_bytes() == before
    original = Path.replace

    def failed(source, target):
        if target == profile_path(root):
            raise OSError("synthetic publication failure")
        return original(source, target)

    monkeypatch.setattr(Path, "replace", failed)
    with pytest.raises(OSError, match="publication"):
        configure(root, path, digest)
    assert profile_path(root).read_bytes() == before
    assert not list(profile_path(root).parent.glob("*.tmp"))


def test_runtime_load_failure_is_not_readiness_and_retry_works(tmp_path, monkeypatch):
    path = tmp_path / "model.npz"
    digest = fixture_checkpoint(path)
    root = tmp_path / "data"
    configure(root, path, digest)
    previous = profile_path(root).read_bytes()
    broken = tmp_path / "broken-runtime"
    (broken / "scipy").mkdir(parents=True)
    (broken / "scipy/__init__.py").write_text("raise ImportError('synthetic-private-runtime-path')")
    monkeypatch.setenv("PYTHONPATH", str(broken))
    service = CompletionService(data_root=root)
    with pytest.raises(ValueError, match="could not load") as failure:
        service.load("runtime-check", "broken-runtime")
    assert "private-runtime" not in str(failure.value)
    assert not service.capabilities()["loaded"] and service.active is None
    assert service.capabilities()["state"] == "load-error"
    assert service.capabilities()["available"], "A failed load must permit an explicit retry"
    with pytest.raises(ValueError):
        configure(root, path, digest)
    assert profile_path(root).read_bytes() == previous
    monkeypatch.delenv("PYTHONPATH")
    assert service.load("runtime-check", "repaired-runtime")["loaded"]
    service.unload()


def test_readiness_is_read_only_and_distinguishes_file_runtime_and_config(tmp_path, monkeypatch):
    root = tmp_path / "no-data"
    assert CompletionService(data_root=root).capabilities()["state"] == "unconfigured"
    assert not root.exists()
    path = tmp_path / "missing.npz"
    service = CompletionService(path, "0" * 64)
    assert service.capabilities()["state"] == "checkpoint-missing"
    path.touch()
    assert service.capabilities()["state"] == "checkpoint-invalid"
    digest = fixture_checkpoint(path)
    service = CompletionService(path, digest)
    monkeypatch.setattr("mashi.ml_service.subprocess.Popen", lambda *a, **k: pytest.fail("worker"))
    assert service.capabilities()["state"] == "off"
    monkeypatch.setattr("mashi.ml_service.importlib.util.find_spec", lambda _: None)
    assert service.capabilities()["state"] == "runtime-missing"
    assert not service.capabilities()["available"]
    assert CompletionService(path, "not-a-hash").capabilities()["state"] == "configuration-error"


@pytest.mark.parametrize(
    "payload",
    [
        b'{"version":1,"version":1,"enabled":false}',
        b'{"version":2,"enabled":false}',
        b"[]",
        b'{"version":true,"enabled":false}',
        b"x" * 8193,
        b"[" * 3000,
        b'{"version":1,"enabled":true,"checkpoint":"relative.npz","sha256":"bad"}',
    ],
)
def test_bad_persisted_settings_fail_closed_without_blocking_core(tmp_path, payload):
    target = profile_path(tmp_path)
    target.parent.mkdir()
    target.write_bytes(payload)
    service = CompletionService(data_root=tmp_path)
    assert service.capabilities()["state"] == "configuration-error"
    assert target.read_bytes() == payload
    with TestClient(create_app(tmp_path, testing=True)) as client:
        client.headers["x-mashi-token"] = client.get("/api/session").json()["token"]
        doc, base, _ = ready(client)
        assert client.post(base + "/export/ufo?include_fixture=true").status_code == 200
        assert not client.get("/api/completion/capabilities").json()["available"]


def test_profile_links_refused_and_environment_override_is_explicit(tmp_path, monkeypatch):
    path = tmp_path / "model.npz"
    digest = fixture_checkpoint(path)
    root = tmp_path / "data"
    configure(root, path, digest)
    saved = profile_path(root).read_bytes()
    profile_path(root).unlink()
    external = tmp_path / "private-settings.json"
    external.write_bytes(saved)
    profile_path(root).symlink_to(external)
    assert CompletionService(data_root=root).capabilities()["state"] == "configuration-error"
    with pytest.raises(ValueError, match="symbolic"):
        disable(root)
    assert external.read_bytes() == saved
    monkeypatch.setenv("MASHI_COMPLETION_CHECKPOINT", str(path))
    monkeypatch.setenv("MASHI_COMPLETION_SHA256", digest)
    cap = CompletionService(data_root=root).capabilities()
    assert cap["state"] == "off" and cap["configuration_source"] == "environment"
    with pytest.raises(ValueError, match="Environment"):
        configure(root, path, digest)
    with pytest.raises(ValueError, match="Environment"):
        disable(root)
    assert external.read_bytes() == saved


def test_busy_reload_keeps_the_already_loaded_model(tmp_path):
    path = tmp_path / "model.npz"
    service = CompletionService(path, fixture_checkpoint(path))
    service.load("project", "load-first")
    before = service.model
    service.active = {"project": "project", "job": "other-request", "process": None}
    with pytest.raises(ValueError):
        service.load("project", "concurrent-load")
    assert service.model is before and service.active["job"] == "other-request"
    service.active = None
    service.unload()


def test_profile_is_not_in_project_backup_or_browser_configuration(tmp_path):
    path = tmp_path / "external.npz"
    digest = fixture_checkpoint(path)
    root = tmp_path / "data"
    configure(root, path, digest)
    with TestClient(create_app(root, testing=True)) as client:
        client.headers["x-mashi-token"] = client.get("/api/session").json()["token"]
        doc, base, _ = ready(client)
        cap = client.get("/api/completion/capabilities").json()
        assert cap["available"] and not cap["loaded"]
        assert (
            client.post(
                base + "/completion/load",
                json={"revision": doc["revision"], "job_id": "x", "checkpoint": str(path)},
            ).status_code
            == 422
        )
        response = client.post(base + "/backup", json={"revision": doc["revision"]})
        assert response.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        assert not any("profile.json" in n or n.endswith(".npz") for n in archive.namelist())
        assert all(str(path).encode() not in archive.read(n) for n in archive.namelist())


def test_module_cli_status_and_configuration_have_no_automatic_activation(tmp_path):
    root = tmp_path / "data"
    command = [sys.executable, "-m", "mashi.completion_setup", "--data-dir", str(root)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
    assert json.loads(result.stdout)["state"] == "unconfigured" and not root.exists()
    path = tmp_path / "model.npz"
    digest = fixture_checkpoint(path)
    result = subprocess.run(
        command + ["--checkpoint", str(path), "--sha256", digest],
        capture_output=True,
        text=True,
        timeout=20,
        check=True,
    )
    assert json.loads(result.stdout)["state"] == "off"
    assert not CompletionService(data_root=root).capabilities()["loaded"]
    result = subprocess.run(
        command + ["--disable"], capture_output=True, text=True, timeout=10, check=True
    )
    assert json.loads(result.stdout)["state"] == "unconfigured" and path.is_file()
