"""Explicit local completion configuration. Never installs code or copies weights."""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

MAX_PROFILE = 8192


def profile_path(root):
    return Path(root) / "completion" / "profile.json"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate completion settings")
        result[key] = value
    return result


def read_profile(root):
    target = profile_path(root)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("Completion settings cannot be a symbolic link")
    if not target.exists():
        return None
    try:
        with target.open("rb") as stream:
            data = stream.read(MAX_PROFILE + 1)
        if len(data) > MAX_PROFILE:
            raise ValueError("Completion settings exceed their size limit")
        value = json.loads(data, object_pairs_hook=unique_object)
        if (
            not isinstance(value, dict)
            or type(value.get("version")) is not int
            or value["version"] != 1
            or type(value.get("enabled")) is not bool
        ):
            raise ValueError("Unsupported completion settings")
        if not value["enabled"] and set(value) == {"version", "enabled"}:
            return value
        if (
            set(value) != {"version", "enabled", "checkpoint", "sha256"}
            or not value["enabled"]
            or not isinstance(value["checkpoint"], str)
            or not 1 <= len(value["checkpoint"]) <= 4096
            or "\0" in value["checkpoint"]
            or not Path(value["checkpoint"]).is_absolute()
            or not isinstance(value["sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"])
        ):
            raise ValueError("Invalid completion settings")
        return value
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        raise ValueError(
            "Completion settings could not be read. Review local model setup."
        ) from error


def write_profile(root, value):
    payload = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    if len(payload) > MAX_PROFILE:
        raise ValueError("Completion settings exceed their size limit")
    target = profile_path(root)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("Completion settings cannot replace a symbolic link")
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix="profile-", suffix=".tmp", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def configure(root, checkpoint, digest):
    from .ml_service import CompletionService

    if os.environ.get("MASHI_COMPLETION_CHECKPOINT") or os.environ.get("MASHI_COMPLETION_SHA256"):
        raise ValueError(
            "Environment model settings take precedence. Remove them before changing saved model setup."
        )
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Supply the checkpoint's reviewed 64-character SHA-256.")
    path = Path(checkpoint).expanduser().resolve()
    if len(str(path)) > 4096:
        raise ValueError("Checkpoint path is too long")
    service = CompletionService(path, digest)
    try:
        if not service.capabilities()["available"]:
            raise ValueError(service.capabilities()["reason"])
        result = service.load("local-model-setup", str(uuid.uuid4()))
        model = result["model"]
        write_profile(
            root, {"version": 1, "enabled": True, "checkpoint": str(path), "sha256": digest}
        )
        return {
            "configured": True,
            "loaded": False,
            "state": "off",
            "format_version": model["format_version"],
            "profile": model["profile"],
            "sequence_count": len(model["labels"]),
            "sha256": digest,
            "checkpoint_source_known": model["terms"]["checkpoint_source_known"],
            "checkpoint_distribution": model["terms"]["checkpoint_distribution"],
        }
    finally:
        service.unload()


def disable(root):
    if os.environ.get("MASHI_COMPLETION_CHECKPOINT") or os.environ.get("MASHI_COMPLETION_SHA256"):
        raise ValueError(
            "Environment model settings take precedence. Remove them before disabling saved model setup."
        )
    write_profile(root, {"version": 1, "enabled": False})
    return {"configured": False, "loaded": False, "state": "unconfigured"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", type=Path, default=Path(os.environ.get("MASHI_DATA_DIR", ".mashi"))
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--checkpoint", type=Path)
    group.add_argument("--disable", action="store_true")
    parser.add_argument("--sha256")
    args = parser.parse_args(argv)
    if bool(args.checkpoint) != bool(args.sha256):
        parser.error("--checkpoint and --sha256 must be supplied together")
    try:
        if args.checkpoint:
            result = configure(args.data_dir, args.checkpoint, args.sha256)
        elif args.disable:
            result = disable(args.data_dir)
        else:
            from .ml_service import CompletionService

            result = CompletionService(data_root=args.data_dir).capabilities()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
