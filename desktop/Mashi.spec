"""One-directory macOS bundle; run only through scripts/build_desktop.py."""

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
datas = collect_data_files("mashi") + collect_data_files("webview")
datas += [(str(root / "build" / "desktop-notices"), "notices")]
datas += copy_metadata("pywebview")
hidden = ["webview.platforms.cocoa", "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl", "mashi.ml_engine"]
for package in ("fontmake", "fontTools", "ufo2ft", "ufoLib2", "fontMath"):
    hidden += collect_submodules(package)
a = Analysis(
    [str(root / "desktop" / "entry.py")], pathex=[str(root)], datas=datas,
    hiddenimports=hidden,
    excludes=["pytest", "httpx", "ruff", "tkinter", "PyQt5", "PyQt6", "PySide6", "gi"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Mashi", debug=False,
    strip=False, upx=False, console=False, target_arch=None, codesign_identity=None,
)
col = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Mashi")
app = BUNDLE(
    col, name="Mashi.app", bundle_identifier="io.github.anima-regem.mashi",
    info_plist={
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "NSHighResolutionCapable": True,
        "NSAppTransportSecurity": {"NSAllowsLocalNetworking": True},
        "NSHumanReadableCopyright": "Mashi contributors. MIT; see bundled notices.",
    },
)
