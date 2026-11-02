# macOS desktop development package

Mashi now has a local macOS app host using Cocoa/WebKit through pywebview, with
Python, the studio, vector tracing and font compilation bundled by PyInstaller.
This is a development package, not a signed/notarized public release. It uses the
same local web UI as the source studio. No model weights, training fonts, OCR
executable or OCR language data are bundled or downloaded at launch.

## Build and run

Build on a Mac with Python 3.12 and `uv` already installed. Initial dependency
installation uses PyPI; capture, manual labels, tracing, editing and export then
work offline. No Apple developer account is needed for this local build.

```sh
uv sync --locked --extra desktop --extra dev --python 3.12
uv run --no-sync python scripts/build_desktop.py
```

The result is `dist/Mashi.app`. Open it in Finder. It includes Python; running the
built app does not require the source checkout, terminal, `uv` or a separately
installed Python. The whole `.app` must stay together. Closing its last window or
choosing **Mashi > Quit Mashi** stops its server. Launch again to reopen projects.

Cloud-managed folders can add Finder metadata during bundle signing. In that case
the build fails verification with an actionable error. Build into a local folder:

```sh
uv run --no-sync python scripts/build_desktop.py --output-dir /tmp/mashi-desktop-dist
```

`/tmp` is disposable and may be cleared at reboot. Preserve a reviewed app in a
normal local folder for ongoing use. The builder uses PyInstaller's normal ad-hoc
local signature and checks `codesign --verify --deep --strict`. This gives the app
no trusted developer identity and is not notarization. It does not change
quarantine, Gatekeeper, network settings or login/startup entries. If macOS blocks
a development build, leave the protection unchanged and use the source studio
while a signed release is prepared:

```sh
uv run --no-sync mashi --port 8001
```

That source command uses the source studio's data folder. To test the desktop
host from source, use `uv run --no-sync mashi-desktop` on macOS.

## Data, recovery and diagnostics

The desktop defaults to `~/Library/Application Support/Mashi`. It does not depend
on Finder's working directory and does not move, replace or import any existing
source checkout's `.mashi` folder. Projects are stored in `mashi.sqlite3`, with
their original images and prepared images in adjacent project directories.

The current source studio has **Project backup → Back up project** and **Import
backup**. The editable `.mashi.zip` includes source photos, all pages and saved
history/settings; import creates a fresh project instead of overwriting one.
See [project backups and migration](PROJECTS_BACKUPS.md). Verify these controls
and their round trip in the exact native build before claiming that artifact
supports them; an older already-built `.app` does not update with source changes.

For a whole-folder recovery copy, quit Mashi and copy the **entire** data folder,
including its database and image directories. Quit an existing source studio
before copying its `.mashi` folder. Copy a complete folder to the desktop data
location only when the destination is new/empty; do not merge databases or
overwrite an existing desktop data folder. Keep the original copy, and quit older
Mashi versions before a newer version edits the same folder. Schema migration is
not an automatic downgrade path.

An explicit alternate folder can be selected at launch:

```sh
/path/to/Mashi.app/Contents/MacOS/Mashi --data-dir /absolute/path/to/Mashi-data
```

`MASHI_DATA_DIR` is also supported for developer launches. The launcher resolves
relative overrides to absolute paths. It takes an OS file lock per data folder;
repeated direct launches exit with a clear message rather than start competing
servers. Finder normally activates the existing app window. Crashes release the
lock automatically. No PID file is used to kill or trust another process.

The desktop starts on `127.0.0.1:48675`, remembers its last successful port, and
keeps the bound socket through startup. If that port belongs to another process,
it selects an available loopback port. It never attaches to or terminates the
source studio on port 8000. A private instance health check must pass before the
window opens. The server is a thread inside the app process, so it cannot survive
an app crash. Bundled font compiler workers also watch their desktop parent's
lifetime. Optional external OCR is a bounded subprocess, not a background service.

Reusing the port preserves the UI origin for unsaved browser recovery data. If a
collision requires a different port, **saved projects remain available**, but old
unsaved browser drafts may belong to the previous origin. Save work before exit
and keep a full-folder backup. The WebKit website cache is OS-managed and is not a
replacement for the project folder.

Choose **Help > Desktop diagnostics** for the project path and honest optional
capability status. `.desktop/desktop.log` rotates at 1 MB with three backups, and
`.desktop/diagnostics.json` records the last launch. The files contain no session
token, image contents, project text, environment dump or HTTP access log. They may
include local folder paths and exception traces; review before sharing them.
Native launch failures show an alert with the log location and source fallback.

The locally tested picker-boundary fix cancels a failed file selection once,
records the delegate exception and shows recovery guidance, rather than allowing
a Python exception to abort Cocoa. The native qualification and its remaining
limits are in [validation](VALIDATION.md#local-native-package-and-picker-boundary).
It covers a fresh profile on a development Mac, not a clean Mac installation.
The core-only development bundle is not the requested integrated alpha: OCR,
completion runtime/model availability, representative handwriting/reader results
and permitted model delivery still need the [alpha gate](TASK_BOARD.md#one-integrated-alpha).

## Optional Malayalam OCR

OCR is not included in the core development artifact. The current source adds
explicit [recognition readiness, language-data setup and correction](RECOGNITION.md);
PKG-004 still requires checking these changes in a rebuilt native bundle.
Manual crops and labels work without it. The capability
check requires an existing local `tesseract` executable **and** Malayalam data;
an installed executable alone is not reported ready. Finder launches also search
the conventional `/opt/homebrew/bin` and `/usr/local/bin` directories.

If you use Homebrew, install its official `tesseract` package separately. You can
provide reviewed local language data at
`~/Library/Application Support/Mashi/ocr/tessdata/mal.traineddata`. Alternatively,
from a source setup, explicitly download the existing pinned official data:

```sh
uv run --no-sync python -m mashi.ocr_setup --output "$HOME/Library/Application Support/Mashi/ocr/tessdata"
```

This command deliberately accesses the network and verifies the pinned hashes;
desktop startup never invokes it. Keep its licence/manifest files. Quit and reopen
Mashi, then check diagnostics. `MASHI_TESSDATA_DIR` can select an existing local
data directory for developer launches. Tesseract and language-data distribution
remain separate installation/licensing work. No missing-letter ML model is
included or represented as ready by this package.

## Reproduce validation

```sh
uv run --no-sync pytest -q
uv run --no-sync ruff check mashi scripts tests
uv run --no-sync python scripts/smoke_desktop.py --app dist/Mashi.app --output build/desktop-smoke.json
```

The smoke uses temporary synthetic data, an unrelated working directory, a minimal
PATH and no OCR data. It checks occupied-port fallback, duplicate launch, static
resources, upload/label/trace, UFO/TTF export, saved-project reopen, port release,
forced crash and post-crash relaunch. It starts and terminates only its own app
processes. No personal project folder is read or modified. `--headless` exists for
these checks; normal app launches display a window.

Manual macOS QA must additionally cover the native file picker, a synthetic page,
label/trace, the native Save dialog, window close, Quit, and reopening the app.
Accessibility and keyboard review across the complete studio remain product work.
The Linux CI suite checks the launcher lifecycle, not Cocoa. The separate desktop
workflow builds and runs the packaged headless smoke on macOS; its result must be
checked for the exact commit rather than assumed from local results.

## Dependency and licence inventory

`uv.lock` records every resolved Python version, source and artifact hash. Each
build creates `build/desktop-notices/inventory.json`, copies wheel-provided
licence/notice files, and includes CPython's licence and Mashi's MIT licence in
`Mashi.app/Contents/Resources/notices`. The inventory covers the whole build
environment, a superset of runtime; it distinguishes external macOS frameworks
and optional unbundled Tesseract. `Mashi-files.json` beside the app records every
regular file's SHA-256 and symlink target. The builder prints the manifest hash.
This supports rebuild/review, not a claim of byte-for-byte reproducible bundles
across macOS, architecture or signing-tool versions.

Desktop additions are pinned `pywebview==6.1`, `pyinstaller==6.22.3` and their locked
transitive dependencies. Existing runtime dependencies remain unchanged. Upstream
wheel metadata and licences are preserved rather than relabelled as Mashi MIT.
Some upstream wheels declare a licence but omit its separate text; the inventory
shows empty `notices` for those packages. Before publishing a binary, review those
gaps, CPython's incorporated components, the PyInstaller bootloader exception,
OpenCV's bundled FFmpeg/native libraries and all redistribution obligations.
This milestone publishes source/build scripts only, not a binary release.

Primary implementation references:
[pywebview API](https://pywebview.flowrl.com/api/),
[PyInstaller macOS packaging notes](https://pyinstaller.org/en/stable/feature-notes.html).

Still needed for a public desktop release: Apple Developer signing/notarization,
architecture/minimum-macOS qualification on clean machines, dependency licence
clearance for binary distribution, app icon/installer and update UX, optional OCR
installation UX, full accessibility QA, and qualification of project
migration/backups in the exact distributed bundle.
