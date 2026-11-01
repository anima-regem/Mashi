import json
from contextlib import asynccontextmanager
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request

import pytest
from fastapi import FastAPI

from mashi.desktop import AlreadyRunning, DesktopServer, InstanceLock, data_directory


def test_absolute_storage_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv("MASHI_DATA_DIR", raising=False)
    expected = data_directory()
    monkeypatch.chdir(tmp_path)
    assert expected == data_directory()
    assert expected.is_absolute()
    monkeypatch.setenv("MASHI_DATA_DIR", str(tmp_path / "existing"))
    assert data_directory() == tmp_path / "existing"
    assert data_directory(tmp_path / "explicit") == tmp_path / "explicit"


def test_lock_releases_without_deleting_project_data(tmp_path):
    project = tmp_path / "project.json"
    project.write_text("keep")
    lock = InstanceLock(tmp_path)
    with pytest.raises(AlreadyRunning):
        InstanceLock(tmp_path)
    lock.close()
    reopened = InstanceLock(tmp_path)
    reopened.close()
    assert project.read_text() == "keep"


def test_server_owns_ephemeral_port_and_health(tmp_path):
    # An occupied unrelated port remains bound throughout launch/shutdown.
    with socket.socket() as existing:
        existing.bind(("127.0.0.1", 0))
        existing.listen()
        server = DesktopServer(FastAPI(), preferred_port=existing.getsockname()[1])
        try:
            url = server.start()
            assert int(url.rsplit(":", 1)[1]) != existing.getsockname()[1]
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(url + "/api/desktop-health") as response:
                assert json.load(response) == {"instance": server.identity}
        finally:
            server.close()
        assert not server.thread.is_alive()
        assert existing.fileno() != -1
        with socket.socket() as probe:
            assert probe.connect_ex(("127.0.0.1", int(url.rsplit(":", 1)[1]))) != 0


def test_startup_failure_is_detected_and_closed():
    @asynccontextmanager
    async def broken(app):
        raise RuntimeError("startup failed")
        yield

    server = DesktopServer(FastAPI(lifespan=broken), startup_timeout=0.3)
    try:
        with pytest.raises(RuntimeError, match="ready"):
            server.start()
    finally:
        server.close()
    assert not server.thread.is_alive()


def test_crash_releases_instance_lock(tmp_path):
    code = (
        "from mashi.desktop import InstanceLock; import sys, time; "
        "lock = InstanceLock(__import__('pathlib').Path(sys.argv[1])); "
        "print('locked', flush=True); time.sleep(30)"
    )
    child = subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], stdout=subprocess.PIPE)
    try:
        assert child.stdout.readline().strip() == b"locked"
        child.kill()
        child.wait(timeout=5)
        reopened = InstanceLock(tmp_path)
        reopened.close()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def test_headless_launch_reopen_and_duplicate(tmp_path):
    root = tmp_path / "projects"
    command = [sys.executable, "-m", "mashi.desktop", "--headless", "--data-dir", str(root)]
    urls = []
    for _ in range(2):
        diagnostic = root / ".desktop" / "diagnostics.json"
        diagnostic.unlink(missing_ok=True)
        child = subprocess.Popen(command, cwd=Path(__file__).parents[1])
        try:
            deadline = time.monotonic() + 30
            while not diagnostic.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            assert diagnostic.exists(), (root / ".desktop" / "desktop.log").read_text()
            document = json.loads(diagnostic.read_text())
            assert document["data_directory"] == str(root)
            assert document["completion"]["available"] is False
            assert "token" not in diagnostic.read_text()
            urls.append(document["server_url"])
            duplicate = subprocess.run(command, timeout=10)
            assert duplicate.returncode == 2
        finally:
            child.terminate()
            child.wait(timeout=10)
        assert child.returncode == 0
    assert (root / "mashi.sqlite3").is_file()
