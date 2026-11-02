import csv
import io
import math
import os
import shutil
import subprocess
from pathlib import Path
from .ocr_setup import managed_directory


def tessdata_args(data_root=None):
    explicit = os.environ.get("MASHI_TESSDATA_DIR")
    root = Path(data_root or os.environ.get("MASHI_DATA_DIR", ".mashi"))
    managed = managed_directory(root)
    local = managed if managed.exists() else root / "ocr" / "tessdata"
    folder = Path(explicit) if explicit else local
    return ["--tessdata-dir", str(folder.resolve())] if explicit or folder.is_dir() else []


def capabilities(data_root=None):
    root = Path(data_root or os.environ.get("MASHI_DATA_DIR", ".mashi"))
    can_setup = not os.environ.get("MASHI_TESSDATA_DIR") and not managed_directory(root).exists()

    def status(state, reason, *, available=False):
        return {
            "available": available,
            "state": state,
            "reason": reason,
            "can_setup": can_setup and state in {"missing-data", "data-error"},
        }

    executable = shutil.which("tesseract")
    if not executable:
        return status(
            "missing-engine",
            "Word recognition is not installed. Label crops manually or see recognition help.",
        )
    try:
        result = subprocess.run(
            [executable, *tessdata_args(root), "--list-langs"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=True,
        )
        langs = result.stdout.decode("utf-8").splitlines()
        if "mal" not in langs:
            return status(
                "missing-data",
                "Malayalam recognition data is missing. Label crops manually or see recognition help.",
            )
    except (subprocess.SubprocessError, OSError, UnicodeError):
        return status(
            "engine-error",
            "Word recognition could not start. Label crops manually or see recognition help.",
        )
    try:
        # --list-langs can list an unreadable/corrupt model. Verify it can initialize.
        subprocess.run(
            [executable, *tessdata_args(root), "-l", "mal", "--print-parameters"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=True,
        )
    except (subprocess.SubprocessError, OSError, UnicodeError):
        return status(
            "data-error",
            "Word recognition could not start. Label crops manually or see recognition help.",
        )
    return status(
        "ready",
        "Word suggestions are ready. Review each crop and label; handwriting may be missed or misread.",
        available=True,
    )


def recognize(path, *, data_root=None):
    cap = capabilities(data_root) if data_root is not None else capabilities()
    if not cap["available"]:
        raise ValueError(cap["reason"])
    try:
        # Resolve aliases for the native reader; decode TSV, never diagnostic bytes.
        result = subprocess.run(
            [
                shutil.which("tesseract"),
                str(Path(path).resolve()),
                "stdout",
                *tessdata_args(data_root),
                "-l",
                "mal",
                "--psm",
                "11",
                "-c",
                "tessedit_create_tsv=1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=True,
        )
        output = result.stdout.decode("utf-8")
    except (subprocess.SubprocessError, OSError, UnicodeError) as error:
        raise ValueError(
            "Word recognition could not finish. Try again or label crops manually."
        ) from error
    suggestions = []
    rows = csv.DictReader(io.StringIO(output), delimiter="\t")
    if not {"level", "left", "top", "width", "height", "conf", "text"}.issubset(
        rows.fieldnames or []
    ):
        raise ValueError(
            "Word recognition returned no usable crop positions. Try again or label crops manually."
        )
    for row in rows:
        if row["level"] == "5" and row.get("text", "").strip():
            try:
                x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
                confidence = float(row["conf"])
                if (
                    x < 0
                    or y < 0
                    or w <= 0
                    or h <= 0
                    or not math.isfinite(confidence)
                    or not -1 <= confidence <= 100
                    or len(row["text"]) > 1024
                ):
                    raise ValueError()
            except (ValueError, TypeError) as error:
                raise ValueError(
                    "Word recognition returned invalid crop data. Try again or label crops manually."
                ) from error
            suggestions.append(
                {
                    "box": [x, y, x + w, y + h],
                    "raw_text": row["text"],
                    "confidence": confidence,
                    "granularity": "word",
                }
            )
            if len(suggestions) == 1000:
                break
    return suggestions
