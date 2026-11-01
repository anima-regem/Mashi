"""Exercise the built app's offline API and lifecycle without touching personal projects."""

import argparse
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile

from PIL import Image, ImageDraw


def wait_for_start(child, state):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline and child.poll() is None:
        try:
            document = json.loads((state / "diagnostics.json").read_text())
            if document.get("pid") == child.pid:
                return document
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    log = state / "desktop.log"
    raise RuntimeError(log.read_text() if log.exists() else "App did not write diagnostics")


def port_closed(url):
    with socket.socket() as probe:
        probe.settimeout(1)
        return probe.connect_ex(("127.0.0.1", int(url.rsplit(":", 1)[1]))) != 0


def smoke(executable, root):
    state = root / ".desktop"
    state.mkdir(parents=True)
    command = [str(executable), "--headless", "--data-dir", str(root)]
    environment = dict(os.environ)
    for key in ("PYTHONHOME", "PYTHONPATH", "MASHI_DATA_DIR", "MASHI_TESSDATA_DIR"):
        environment.pop(key, None)
    environment["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
    # No OCR data is supplied. Explicitly exercise honest unavailable diagnostics.
    environment["MASHI_TESSDATA_DIR"] = str(root / "no-ocr-data")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    checks = []
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        occupied_url = f"http://127.0.0.1:{occupied.getsockname()[1]}"
        (state / "diagnostics.json").write_text(json.dumps({"server_url": occupied_url}))
        child = subprocess.Popen(command, cwd=root, env=environment)
        try:
            diagnostic = wait_for_start(child, state)
            url = diagnostic["server_url"]
            assert url != occupied_url
            checks.append("occupied preferred port falls back without touching its listener")
            duplicate = subprocess.run(command, cwd=root, env=environment, timeout=10)
            assert duplicate.returncode == 2
            checks.append("duplicate launch rejected by OS lock")

            def request(path, *, method="GET", data=None, token=None):
                headers = {}
                if token:
                    headers["X-Mashi-Token"] = token
                if isinstance(data, dict):
                    data = json.dumps(data).encode()
                    headers["Content-Type"] = "application/json"
                with opener.open(urllib.request.Request(
                    url + path, data=data, headers=headers, method=method,
                ), timeout=70) as response:
                    return response.read()

            for path in ("/", "/static/app.js", "/static/outline.js", "/static/style.css"):
                assert request(path)
            checks.append("bundled HTML, JavaScript and CSS served from unrelated cwd")
            session = json.loads(request("/api/session"))
            assert not session["ocr"]["available"]
            assert not diagnostic["completion"]["available"]
            checks.append("OCR without language data and absent ML model reported unavailable")
            token = session["token"]
            image = Image.new("RGB", (240, 180), "white")
            ImageDraw.Draw(image).ellipse((30, 20, 170, 150), outline="black", width=12)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            doc = json.loads(request(
                "/api/projects?source=synthetic-fixture", method="POST", data=buffer.getvalue(),
                token=token,
            ))
            project_id = doc["id"]
            region = doc["regions"][0]
            base = f"/api/projects/{project_id}"
            doc = json.loads(request(base + f"/regions/{region['id']}", method="PUT", data={
                "box": region["box"], "label": "ക", "confirmed": True,
                "revision": region["revision"],
            }, token=token))
            region = doc["regions"][0]
            doc = json.loads(request(base + f"/regions/{region['id']}/trace", method="POST", data={
                "revision": region["revision"], "threshold": 180,
            }, token=token))
            assert doc["regions"][0]["vector"]["paths"]
            checks.append("synthetic PNG uploaded, labelled and vector traced")
            for kind in ("ufo", "ttf"):
                archive_data = request(base + f"/export/{kind}?include_fixture=true", method="POST",
                                       token=token)
                with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
                    report = json.loads(archive.read("coverage.json"))
                    assert report["synthetic_test_export"]
                    assert any(name.endswith(".ttf" if kind == "ttf" else ".glif")
                               for name in archive.namelist())
                checks.append(f"offline {kind.upper()} export from bundled runtime")
            child.terminate()
            child.wait(timeout=10)
            assert child.returncode == 0 and port_closed(url)
            checks.append("graceful close releases only the app server")

            child = subprocess.Popen(command, cwd=root, env=environment)
            reopened = wait_for_start(child, state)
            assert reopened["server_url"] == url
            assert project_id in {p["id"] for p in json.loads(request("/api/projects"))}
            checks.append("reopen reuses port and preserves the saved project")
            child.kill()
            child.wait(timeout=10)
            assert port_closed(url)
            checks.append("forced crash leaves no orphan server")

            child = subprocess.Popen(command, cwd=root, env=environment)
            wait_for_start(child, state)
            assert project_id in {p["id"] for p in json.loads(request("/api/projects"))}
            checks.append("post-crash launch releases lock and preserves the saved project")
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=10)
    return {"status": "passed", "checks": checks, "packaged": diagnostic["packaged"],
            "ocr": diagnostic["ocr"], "data": "temporary synthetic data only"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, required=True, help="Path to Mashi.app")
    parser.add_argument("--output", type=Path, required=True, help="Write the JSON smoke result")
    args = parser.parse_args()
    executable = args.app.resolve() / "Contents" / "MacOS" / "Mashi"
    with tempfile.TemporaryDirectory(prefix="mashi-desktop-smoke-") as directory:
        report = smoke(executable, Path(directory))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
