import csv
import io
import os
import shutil
import subprocess
from pathlib import Path


def tessdata_args():
    explicit = os.environ.get("MASHI_TESSDATA_DIR")
    local = Path(os.environ.get("MASHI_DATA_DIR", ".mashi")) / "ocr" / "tessdata"
    folder = Path(explicit) if explicit else local
    return ["--tessdata-dir", str(folder.resolve())] if explicit or folder.is_dir() else []


def capabilities():
    executable = shutil.which("tesseract")
    if not executable:
        return {"available": False, "reason": "Word suggestions are unavailable. Label crops manually."}
    try:
        result = subprocess.run(
            [executable, *tessdata_args(), "--list-langs"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        langs = result.stdout.splitlines()
        if "mal" not in langs:
            return {
                "available": False,
                "reason": "Malayalam word suggestions are unavailable. Label crops manually.",
            }
    except (subprocess.SubprocessError, OSError):
        return {"available": False, "reason": "Word recognition could not start. Label crops manually."}
    return {"available": True, "reason": "Review suggested words before confirming them."}


def recognize(path):
    cap = capabilities()
    if not cap["available"]:
        raise ValueError(cap["reason"])
    try:
        result = subprocess.run(
            [
                shutil.which("tesseract"),
                str(path),
                "stdout",
                *tessdata_args(),
                "-l",
                "mal",
                "--psm",
                "11",
                "-c",
                "tessedit_create_tsv=1",
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as error:
        raise ValueError("Word recognition could not finish. Try again or label crops manually.") from error
    suggestions = []
    rows = csv.DictReader(io.StringIO(result.stdout), delimiter="\t")
    if not {"level", "left", "top", "width", "height", "conf", "text"}.issubset(
        rows.fieldnames or []
    ):
        raise ValueError(
            "Word recognition returned no usable crop positions. Try again or label crops manually."
        )
    for row in rows:
        if row["level"] == "5" and row.get("text", "").strip():
            x, y, w, h = (int(row[k]) for k in ("left", "top", "width", "height"))
            suggestions.append(
                {
                    "box": [x, y, x + w, y + h],
                    "raw_text": row["text"],
                    "confidence": float(row["conf"]),
                    "granularity": "word",
                }
            )
    return suggestions[:1000]
