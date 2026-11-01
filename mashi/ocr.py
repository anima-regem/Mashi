import csv
import io
import shutil
import subprocess


def capabilities():
    executable = shutil.which("tesseract")
    if not executable:
        return {"available": False, "reason": "Tesseract is not installed. Manual labels work."}
    try:
        result = subprocess.run(
            [executable, "--list-langs"], capture_output=True, text=True, timeout=10, check=True
        )
        langs = result.stdout.splitlines()
        if "mal" not in langs:
            return {
                "available": False,
                "reason": "Install Tesseract’s Malayalam (mal) language data.",
            }
    except (subprocess.SubprocessError, OSError):
        return {"available": False, "reason": "Tesseract could not be started."}
    return {"available": True, "reason": "Local Tesseract mal; word suggestions need correction."}


def recognize(path):
    cap = capabilities()
    if not cap["available"]:
        raise ValueError(cap["reason"])
    try:
        result = subprocess.run(
            [shutil.which("tesseract"), str(path), "stdout", "-l", "mal", "--psm", "11", "tsv"],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
    except (subprocess.SubprocessError, OSError) as error:
        raise ValueError("Local OCR failed or exceeded 60 seconds; use manual crops") from error
    suggestions = []
    for row in csv.DictReader(io.StringIO(result.stdout), delimiter="\t"):
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
