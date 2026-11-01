"""Offline desktop host. The server lives in this process, never a shared studio PID."""

import argparse
import errno
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

LOG = logging.getLogger("mashi.desktop")


def data_directory(override=None):
    """An absolute, user-specific location, independent of Finder's cwd."""
    if override or os.environ.get("MASHI_DATA_DIR"):
        return Path(override or os.environ["MASHI_DATA_DIR"]).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Mashi"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "mashi"


class AlreadyRunning(RuntimeError):
    pass


class InstanceLock:
    """OS-owned lock: a crash releases it; stale PID files never trigger a kill."""

    def __init__(self, directory):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = (directory / "instance.lock").open("a+")
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self.file.close()
            raise AlreadyRunning(
                "Mashi is already open for this data folder. Select its window in the Dock."
            ) from error

    def close(self):
        self.file.close()


def configure_logging(state):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    handler = RotatingFileHandler(state / "desktop.log", maxBytes=1_000_000, backupCount=3)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)
    # Never enable API access logs: URLs, filenames and session responses are unnecessary.
    logging.getLogger("uvicorn.access").disabled = True
    return handler


def local_ocr_environment():
    # Finder does not inherit a shell PATH. These are conventional local install locations;
    # this only discovers an existing executable, never installs or downloads anything.
    entries = os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin").split(os.pathsep)
    for entry in ("/opt/homebrew/bin", "/usr/local/bin"):
        if entry not in entries:
            entries.append(entry)
    os.environ["PATH"] = os.pathsep.join(entries)


class DesktopServer:
    def __init__(self, app, *, preferred_port=0, startup_timeout=30):
        import uvicorn

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Keep the same socket from bind through serve. No check-then-bind port race.
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.socket.bind(("127.0.0.1", preferred_port))
        except OSError as error:
            if error.errno != errno.EADDRINUSE or preferred_port == 0:
                self.socket.close()
                raise
            self.socket.bind(("127.0.0.1", 0))
            LOG.warning("Previous desktop port is occupied; using another local port")
        self.socket.listen(128)
        self.url = f"http://127.0.0.1:{self.socket.getsockname()[1]}"
        self.identity = secrets.token_hex(24)
        self.error = None
        self.startup_timeout = startup_timeout
        identity = self.identity

        @app.get("/api/desktop-health", include_in_schema=False)
        def desktop_health():
            return {"instance": identity}

        self.server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", log_config=None, access_log=False,
                loop="asyncio", http="h11", ws="none", timeout_graceful_shutdown=3,
            )
        )
        self.thread = threading.Thread(target=self._serve, name="mashi-api", daemon=True)

    def _serve(self):
        try:
            self.server.run(sockets=[self.socket])
        except BaseException as error:
            self.error = error
            LOG.exception("Local server stopped unexpectedly")

    def start(self):
        self.thread.start()
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if not self.thread.is_alive():
                raise RuntimeError("The local server exited before it was ready") from self.error
            try:
                with opener.open(self.url + "/api/desktop-health", timeout=0.3) as response:
                    if json.load(response).get("instance") == self.identity:
                        LOG.info("Local server ready")
                        return self.url
            except (OSError, urllib.error.URLError, ValueError):
                pass
            time.sleep(0.05)
        raise RuntimeError("The local server did not become ready within 30 seconds")

    def close(self):
        self.server.should_exit = True
        if self.thread.ident is not None:
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                self.server.force_exit = True
                self.thread.join(timeout=1)
                LOG.warning("Server shutdown exceeded its deadline")
        self.socket.close()


def write_diagnostics(state, root, url):
    from . import ocr

    document = {
        "desktop_version": "0.1.0",
        "packaged": bool(getattr(sys, "frozen", False)),
        "platform": sys.platform,
        "data_directory": str(root),
        "server_url": url,
        "pid": os.getpid(),
        "ocr": ocr.capabilities(),
        "completion": {
            "available": False,
            "reason": "This desktop package does not bundle an ML model or download weights.",
        },
        "network": "Loopback only. No runtime downloads, telemetry or remote UI assets.",
    }
    # No session token, image metadata, project text or environment variables are recorded.
    target = state / "diagnostics.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return document


def alert(title, message):
    """Native launch failure UI also works when Python/pywebview cannot be imported."""
    if sys.stderr is not None:
        print(f"{title}: {message}", file=sys.stderr)
    if sys.platform == "darwin":
        script = (
            'on run argv\ndisplay alert (item 1 of argv) message (item 2 of argv) '
            'buttons {"OK"} default button "OK"\nend run'
        )
        try:
            subprocess.run(
                ["/usr/bin/osascript", "-e", script, title, message],
                check=False, capture_output=True, timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def frozen_tool_dispatch(argv):
    """Existing exporter uses sys.executable -m fontmake; a frozen exe is not Python."""
    if argv[:2] == ["-m", "fontmake"]:
        owner = os.environ.get("MASHI_DESKTOP_OWNER_PID")
        if owner == str(os.getppid()):
            def watch_parent():
                while owner == str(os.getppid()):
                    time.sleep(0.25)
                # Exit this compiler only, if its desktop parent crashed or quit.
                os._exit(1)

            threading.Thread(target=watch_parent, name="mashi-compiler-owner", daemon=True).start()
        from fontmake.__main__ import main as fontmake_main

        fontmake_main(argv[2:])
        return True
    return False


def run_window(server, root, state):
    import AppKit
    from PyObjCTools import AppHelper
    import webview
    from webview.menu import Menu, MenuAction

    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        "Mashi", server.url, width=1280, height=860, min_size=(960, 640),
        background_color="#f5f1e8",
    )
    closed = threading.Event()
    window.events.closed += closed.set

    def closing():
        # Cocoa Quit terminates directly instead of returning from webview.start.
        # Drain owned requests before allowing that termination or closing the window.
        closed.set()
        server.close()

    window.events.closing += closing

    def window_alert(title, message):
        finished = threading.Event()

        def show():
            try:
                dialog = AppKit.NSAlert.alloc().init()
                dialog.setMessageText_(title)
                dialog.setInformativeText_(message)
                dialog.addButtonWithTitle_("OK")
                dialog.runModal()
            finally:
                finished.set()

        if threading.current_thread() is threading.main_thread():
            show()
        else:
            AppHelper.callAfter(show)
            finished.wait(120)

    def diagnostics():
        document = write_diagnostics(state, root, server.url)
        status = "Available" if document["ocr"]["available"] else document["ocr"]["reason"]
        window_alert(
            "Mashi desktop diagnostics",
            f"Projects: {root}\nLogs: {state / 'desktop.log'}\nOCR: {status}\n"
            "ML suggestions: no model bundled. Manual labels, tracing and export work offline.",
        )

    def watch_server():
        while not closed.wait(0.5):
            if not server.thread.is_alive():
                LOG.error("Server exited while the desktop window was open")
                window_alert(
                    "Mashi server stopped", f"Reopen Mashi. Diagnostic log: {state / 'desktop.log'}"
                )
                window.destroy()
                break

    # The default macOS application menu supplies standard Quit/Hide actions.
    menu = [Menu("Help", [MenuAction("Desktop diagnostics", diagnostics)])]
    webview.start(
        watch_server, gui="cocoa", debug=False, private_mode=False,
        storage_path=str(state / "WebKit"), menu=menu,
    )


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if frozen_tool_dispatch(argv):
        return 0
    parser = argparse.ArgumentParser(description="Open the offline Mashi desktop studio")
    parser.add_argument("--data-dir", type=Path, help="Explicit existing or new project folder")
    parser.add_argument("--headless", action="store_true", help="Serve without a window for checks")
    args = parser.parse_args(argv)
    root = data_directory(args.data_dir)
    state = root / ".desktop"
    lock = server = handler = None
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = InstanceLock(state)
        handler = configure_logging(state)
        # Set before importing app: the legacy module also constructs its default app.
        os.environ["MASHI_DATA_DIR"] = str(root)
        os.environ["MASHI_DESKTOP_OWNER_PID"] = str(os.getpid())
        local_ocr_environment()
        from .app import create_app

        port = 48675
        try:
            previous = json.loads((state / "diagnostics.json").read_text())
            candidate = int(previous["server_url"].rsplit(":", 1)[1])
            if 1024 <= candidate <= 65535:
                port = candidate
        except (OSError, ValueError, KeyError, TypeError):
            pass
        server = DesktopServer(create_app(root), preferred_port=port)
        server.start()
        write_diagnostics(state, root, server.url)
        LOG.info("Desktop started (packaged=%s)", bool(getattr(sys, "frozen", False)))
        if args.headless:
            stopped = threading.Event()
            previous = {}
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, lambda *_: stopped.set())
            try:
                while not stopped.wait(0.2):
                    if not server.thread.is_alive():
                        raise RuntimeError("Local server stopped")
            finally:
                for sig, callback in previous.items():
                    signal.signal(sig, callback)
        else:
            run_window(server, root, state)
        return 0
    except AlreadyRunning as error:
        if not args.headless:
            alert("Mashi is already open", str(error))
        return 2
    except Exception:
        LOG.exception("Desktop launch failed")
        if not args.headless:
            alert(
                "Mashi could not open",
                f"Reopen Mashi after checking {state / 'desktop.log'}.\n"
                "Your saved project folder has not been removed.\n"
                "Source fallback: uv run mashi --port 8001 (uses the source studio data folder).",
            )
        return 1
    finally:
        if server:
            server.close()
        if lock:
            lock.close()
        if handler:
            logging.getLogger().removeHandler(handler)
            handler.close()


if __name__ == "__main__":
    raise SystemExit(main())
