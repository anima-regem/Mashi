"""Editable project archives: bounded inspection, staged import, no extractall."""

from contextlib import contextmanager
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import tempfile
import threading
import time
import uuid
import warnings
import zipfile
import zlib

from PIL import Image

from .imaging import MAX_BYTES, MAX_PIXELS, validate_box
from .models import RegionInput, TypographyInput, PreparationOptions
from .font_metrics import TypographyOptions
from .projects import MAX_PAGES, MAX_DOCUMENT, document, schema, view
from .tracing import validate_paths
from .ml_service import LICENSE_ROOT

MAX_ARCHIVE = 256 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_ASSET = 64 * 1024 * 1024
MAX_ENTRIES = 4096
ASSET_KEYS = {"image_asset", "source_asset", "original_asset", "raster_asset", "asset"}
guard = threading.Lock()


@contextmanager
def operation():
    if not guard.acquire(blocking=False):
        raise ValueError("Another backup operation is running. Try again shortly.")
    try:
        yield
    finally:
        guard.release()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_member(archive, name, limit=MAX_ASSET):
    """Bound each inflate call as well as the directory's claimed output size."""
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise ValueError("Backup member exceeds its size limit")
    pieces, total = [], 0
    try:
        with archive.open(info) as stream:
            while True:
                piece = stream.read(min(65536, limit + 1 - total))
                if not piece:
                    break
                pieces.append(piece)
                total += len(piece)
                if total > limit:
                    raise ValueError("Expanded backup member exceeds its size limit")
    except (RuntimeError, NotImplementedError, zlib.error) as error:
        raise ValueError("Invalid or unsupported compressed backup member") from error
    if total != info.file_size:
        raise ValueError("Expanded backup member size does not match its directory")
    return b"".join(pieces)


def safe_name(name):
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", name):
        raise ValueError("Unsafe backup asset name")
    if not name.endswith((".png", ".bin")):
        raise ValueError("Only project raster assets belong in this backup")
    return name


def json_data(payload):
    if len(payload) > MAX_DOCUMENT:
        raise ValueError("Backup project data exceeds 16 MiB")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON keys in backup")
            result[key] = value
        return result

    try:
        value = json.loads(
            payload,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON")),
        )
    except (ValueError, RecursionError, UnicodeError) as error:
        raise ValueError("Invalid or overly complex backup JSON") from error
    count = 0

    def visit(node, depth=0):
        nonlocal count
        count += 1
        if depth > 40 or count > 200000:
            raise ValueError("Backup JSON is too complex")
        if isinstance(node, dict):
            for key, item in node.items():
                if len(key) > 256:
                    raise ValueError("Backup JSON key is too long")
                visit(item, depth + 1)
        elif isinstance(node, list):
            for item in node:
                visit(item, depth + 1)
        elif isinstance(node, str) and len(node) > 500000:
            raise ValueError("Backup text or outline is too large")
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValueError("Nonfinite backup numbers")

    visit(value)
    return value


def asset_names(project):
    raw = document(project)
    found = set()

    def visit(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ASSET_KEYS and value is not None:
                    found.add(safe_name(value))
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    for page in raw["pages"]:
        found.add(safe_name(page.get("image_asset", "page.png")))
        found.add(safe_name(page.get("original_asset", "original.bin")))
        visit(page)
    return sorted(found)


def _build(store, project, payload):
    assets = []
    total = len(payload)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("project.json", payload)
        for name in asset_names(project):
            path = store.asset(project["id"], name)
            if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ASSET:
                raise ValueError(
                    "A required project image is missing or too large; backup canceled"
                )
            with path.open("rb") as stream:
                data = stream.read(MAX_ASSET + 1)
            if len(data) > MAX_ASSET:
                raise ValueError("A project image changed or exceeds the backup limit")
            total += len(data)
            if total > MAX_TOTAL:
                raise ValueError("Project backup exceeds 512 MiB of image data")
            assets.append({"name": name, "bytes": len(data), "sha256": sha(data)})
            archive.writestr("assets/" + name, data)
        notices = []
        for path in sorted(LICENSE_ROOT.iterdir()):
            if path.is_file():
                data = path.read_bytes()
                notices.append({"name": path.name, "bytes": len(data), "sha256": sha(data)})
                archive.writestr("notices/" + path.name, data)
        manifest = {
            "format": "mashi-editable-project",
            "version": 1,
            "project_sha256": sha(payload),
            "source_images_included": True,
            "model_weights_included": False,
            "assets": assets,
            "notices": notices,
        }
        archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True))
    data = buffer.getvalue()
    if len(data) > MAX_ARCHIVE or len(assets) + len(notices) + 2 > MAX_ENTRIES:
        raise ValueError("Project backup is too large")
    return data


def export_backup(store, project_id):
    with operation():
        payload = store.raw_text(project_id).encode()
        project = json_data(payload)
        schema(project)
        return _build(store, project, payload)


def migration_backup(store, project, exact_payload):
    with operation():
        directory = store.root / ".migrations" / uuid.UUID(project["id"]).hex
        directory.mkdir(parents=True, exist_ok=True)
        name = sha(exact_payload) + ".mashi.zip"
        path = directory / name
        if not path.exists():
            data = _build(store, project, exact_payload)
            descriptor, temporary = tempfile.mkstemp(prefix="pending-", dir=directory)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                if os.name == "posix":
                    for folder in [directory, directory.parent, store.root]:
                        descriptor = os.open(folder, os.O_RDONLY)
                        try:
                            os.fsync(descriptor)
                        finally:
                            os.close(descriptor)
            finally:
                Path(temporary).unlink(missing_ok=True)
        else:
            if path.is_symlink() or path.stat().st_size > MAX_ARCHIVE:
                raise ValueError("Existing legacy backup is unsafe or too large")
            directory_count(path.read_bytes())
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                if (
                    any(
                        i.file_size > MAX_ASSET or i.flag_bits & 1 or i.compress_type not in {0, 8}
                        for i in entries
                    )
                    or sum(i.file_size for i in entries) > MAX_TOTAL
                ):
                    raise ValueError("Existing legacy backup exceeds safe limits")
                if read_member(archive, "project.json", MAX_DOCUMENT) != exact_payload:
                    raise ValueError("Existing migration backup does not match the legacy project")
                manifest = json_data(read_member(archive, "manifest.json", MAX_DOCUMENT))
                names = {"project.json", "manifest.json"}
                for record in manifest["assets"] + manifest["notices"]:
                    member = ("assets/" if record in manifest["assets"] else "notices/") + record[
                        "name"
                    ]
                    data = read_member(archive, member)
                    if len(data) != record["bytes"] or sha(data) != record["sha256"]:
                        raise ValueError("Existing legacy recovery backup is damaged")
                    names.add(member)
                if (
                    names != set(archive.namelist())
                    or len(names) != len(entries)
                    or set(asset_names(project)) != {r["name"] for r in manifest["assets"]}
                ):
                    raise ValueError("Existing legacy recovery backup is incomplete")
        return {
            "from_schema": 1,
            "legacy_document_sha256": sha(exact_payload),
            "backup": str(path.relative_to(store.root)),
            "archive_sha256": sha(path.read_bytes()),
        }


def directory_count(payload):
    # Bound central-directory allocation before constructing ZipInfo objects.
    end = payload.rfind(b"PK\x05\x06", max(0, len(payload) - 65557))
    if end < 0 or end + 22 > len(payload):
        raise ValueError("Invalid project archive")
    _, disk, cd_disk, disk_count, count, size, offset, comment = struct.unpack_from(
        "<4s4H2LH", payload, end
    )
    if (
        disk
        or cd_disk
        or disk_count != count
        or not 2 <= count <= MAX_ENTRIES
        or offset + size != end
        or end + 22 + comment != len(payload)
    ):
        raise ValueError("Unsupported or oversized backup directory")
    cursor, actual = offset, 0
    while cursor < end:
        if cursor + 46 > end or payload[cursor : cursor + 4] != b"PK\x01\x02":
            raise ValueError("Invalid backup directory record")
        name, extra, note = struct.unpack_from("<HHH", payload, cursor + 28)
        if name > 220:
            raise ValueError("Backup path is too long")
        cursor += 46 + name + extra + note
        actual += 1
        if cursor > end or actual > MAX_ENTRIES:
            raise ValueError("Too many backup members")
    if actual != count:
        raise ValueError("Backup directory count mismatch")


def validate_project(project, staged, asset_hashes):
    raw = document(project)
    uuid.UUID(raw["id"])
    if (
        not 1 <= len(raw["pages"]) <= MAX_PAGES
        or not isinstance(raw.get("name", ""), str)
        or len(raw.get("name", "")) > 80
    ):
        raise ValueError("Invalid project pages/name")
    if type(raw["revision"]) is not int or raw["revision"] < 1:
        raise ValueError("Invalid project revision")
    typography = raw.get("typography", {})
    if not isinstance(typography, dict) or set(typography) - set(
        TypographyOptions.__dataclass_fields__
    ):
        raise ValueError("Unknown saved font settings")
    TypographyInput(**typography)
    TypographyOptions(**typography).validate()
    if type(raw.get("typography_revision", 1)) is not int or raw.get("typography_revision", 1) < 1:
        raise ValueError("Invalid saved typography revision")

    def history(entries):
        if not isinstance(entries, list) or any(
            not isinstance(e, dict) or "snapshot" in e and not isinstance(e["snapshot"], dict)
            for e in entries
        ):
            raise ValueError("Invalid saved editing history")
        for entry in entries:
            snapshot = entry.get("snapshot", {})
            if "id" in snapshot and (
                not {"box", "vector", "revision", "confirmed", "active", "provenance", "label"}
                <= snapshot.keys()
                or not isinstance(entry.get("operation"), str)
                or type(entry.get("at")) not in {int, float}
            ):
                raise ValueError("Incomplete restorable sample history")

    history(raw.get("project_history", []))
    if not isinstance(raw.get("proof_text", ""), str) or len(raw.get("proof_text", "")) > 1000:
        raise ValueError("Invalid saved proof text")
    page_ids, row_ids = set(), set()
    for page in raw["pages"]:
        uuid.UUID(page["id"])
        if page["id"] in page_ids or page.get("source_kind") not in {
            "user-upload",
            "synthetic-fixture",
        }:
            raise ValueError("Duplicate page ID or invalid page provenance")
        page_ids.add(page["id"])
        history(page.get("history", []))
        if page.get("preparation") is not None:
            PreparationOptions(**page["preparation"])
        for old in page.get("preparation_history", []):
            if (
                not isinstance(old, dict)
                or not isinstance(old.get("image"), dict)
                or not isinstance(old.get("regions"), list)
            ):
                raise ValueError("Invalid saved preparation state")
        if not isinstance(page["name"], str) or not 1 <= len(page["name"]) <= 80:
            raise ValueError("Invalid page name")
        if type(page["revision"]) is not int or page["revision"] < 1:
            raise ValueError("Invalid page revision")
        if len(page["regions"]) > 5000 or len(page.get("completion_suggestions", [])) > 200:
            raise ValueError("Too many page samples")
        for row in page["regions"] + page.get("completion_suggestions", []):
            uuid.UUID(row["id"])
            if row["id"] in row_ids:
                raise ValueError("Duplicate sample IDs across pages")
            row_ids.add(row["id"])
        if any(r.get("coordinate_space") == "generated-canvas" for r in page["regions"]):
            raise ValueError("Generated canvases must remain in the suggestions collection")
        if page["source_kind"] == "synthetic-fixture" and any(
            r.get("provenance") == "observed" for r in page["regions"]
        ):
            raise ValueError("Current synthetic input cannot become observed handwriting")
        for row in page.get("completion_suggestions", []):
            generation = row["generation"]
            terms = generation["model"]["terms"]
            if (
                type(terms["checkpoint_source_known"]) is not bool
                or not isinstance(generation["observations"], list)
                or not 1 <= len(generation["observations"]) <= 20
                or not isinstance(row["vectorization"]["method"], str)
            ):
                raise ValueError("Invalid generated model/reference state")
            for digest in [generation["model"]["sha256"], generation["image_sha256"]]:
                if not isinstance(digest, str) or not re.fullmatch("[a-f0-9]{64}", digest):
                    raise ValueError("Invalid generated model/image hash")
            if "source_manifest_sha256" not in terms or not row.get("raster_asset"):
                raise ValueError("Generated source/raster provenance is incomplete")
            history(row.get("history", []))
        image_states = [page] + [s for s in page.get("preparation_history", []) if s.get("image")]
        dimensions = [(s["image"]["width"], s["image"]["height"]) for s in image_states]
        if page.get("source_image"):
            dimensions.append((page["source_image"]["width"], page["source_image"]["height"]))
        records, references = {}, []

        # Validate all historical geometry as well as the current selected form.
        def visit(node):
            if isinstance(node, dict):
                if "box" in node and "vector" in node and "id" in node:
                    if (
                        not isinstance(node["box"], list)
                        or len(node["box"]) != 4
                        or any(type(n) is not int for n in node["box"])
                    ):
                        raise ValueError("Invalid half-open saved crop bounds")
                    if node.get("coordinate_space") == "generated-canvas":
                        validate_box(node["box"], 96, 64)
                    else:
                        if not any(
                            0 <= node["box"][0] < node["box"][2] <= w
                            and 0 <= node["box"][1] < node["box"][3] <= h
                            for w, h in dimensions
                        ):
                            raise ValueError("Historical crop is outside its page coordinates")
                    if (
                        type(node.get("revision")) is not int
                        or node["revision"] < 1
                        or type(node.get("confirmed")) is not bool
                        or type(node.get("active")) is not bool
                    ):
                        raise ValueError("Invalid sample revision or confirmation state")
                    if node["confirmed"] and not node.get("label"):
                        raise ValueError("A confirmed sample has no exact label")
                    if node.get("provenance") not in {
                        "observed",
                        "synthetic-fixture",
                        "model-generated",
                        "template-generated",
                    }:
                        raise ValueError("Unknown sample provenance")
                    if node["vector"]:
                        if [node["vector"]["width"], node["vector"]["height"]] != [
                            node["box"][2] - node["box"][0],
                            node["box"][3] - node["box"][1],
                        ]:
                            raise ValueError("Vector canvas does not match its crop")
                        records[(node["id"], node["revision"])] = node
                if "paths" in node:
                    validate_paths(node["paths"])
                    if type(node.get("edited")) is not bool:
                        raise ValueError("Invalid saved outline edit state")
                    for key in ["baseline", "scale", "advance", "width", "height"]:
                        if key not in node or type(node[key]) not in {float, int}:
                            raise ValueError("Invalid saved vector metrics")
                    if (
                        not 0.01 < node["scale"] <= 100
                        or abs(node["baseline"]) > 100000
                        or not 0 <= node["advance"] <= 5000
                        or not 0 < node["width"] <= MAX_PIXELS
                        or not 0 < node["height"] <= MAX_PIXELS
                    ):
                        raise ValueError("Saved vector metrics are out of range")
                if "label" in node:
                    if not isinstance(node["label"], str) or len(node["label"]) > 32:
                        raise ValueError("Invalid exact sample label")
                    RegionInput.valid_label(node["label"])
                if "generation" in node and (
                    node.get("provenance") != "model-generated"
                    or not node.get("not_observed_in_photo")
                ):
                    raise ValueError("Generated provenance cannot be relabelled as captured ink")
                if "raster_asset" in node and asset_hashes.get(node["raster_asset"]) != node.get(
                    "raster_sha256"
                ):
                    raise ValueError("Generated raster hash mismatch")
                for raster in [
                    node.get("raster_asset"),
                    node.get("asset") if "sha256" in node else None,
                ]:
                    if raster:
                        with Image.open(staged / safe_name(raster)) as image:
                            if image.size != (96, 64):
                                raise ValueError(
                                    "Generated/reference raster has the wrong model canvas"
                                )
                if (
                    "asset" in node
                    and "sha256" in node
                    and asset_hashes.get(node["asset"]) != node["sha256"]
                ):
                    raise ValueError("Reference raster hash mismatch")
                if "generation" in node:
                    if (
                        node.get("coordinate_space") != "generated-canvas"
                        or node.get("review_state") not in {"pending", "accepted", "rejected"}
                        or node["confirmed"] != (node["review_state"] == "accepted")
                    ):
                        raise ValueError("Invalid generated review/provenance state")
                    if node["generation"].get("page_id", page["id"]) != page["id"]:
                        raise ValueError("Generated references belong to a different page")
                    references.extend(node["generation"]["observations"])
                for key in [
                    "source_to_original",
                    "working_to_source",
                    "source_to_working",
                    "crop_to_canonical",
                    "canonical_to_vector",
                ]:
                    if key in node:
                        matrix = node[key]
                        if (
                            not isinstance(matrix, list)
                            or len(matrix) != 3
                            or any(
                                not isinstance(r, list)
                                or len(r) != 3
                                or any(
                                    type(n) not in {float, int}
                                    or not math.isfinite(n)
                                    or abs(n) > 1e9
                                    for n in r
                                )
                                for r in matrix
                            )
                        ):
                            raise ValueError("Invalid image coordinate transform")
                        a, b, c = matrix
                        determinant = (
                            a[0] * (b[1] * c[2] - b[2] * c[1])
                            - a[1] * (b[0] * c[2] - b[2] * c[0])
                            + a[2] * (b[0] * c[1] - b[1] * c[0])
                        )
                        if not math.isfinite(determinant) or abs(determinant) < 1e-12:
                            raise ValueError("Image coordinate transform is not invertible")
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(page)
        from .projects import vector_hash

        for ref in references:
            observed = records.get((ref["id"], ref["revision"]))
            if (
                not observed
                or observed["label"] != ref["label"]
                or observed["provenance"] not in {"observed", "synthetic-fixture"}
                or vector_hash(observed["vector"]) != ref["vector_sha256"]
            ):
                raise ValueError("A generated suggestion has a missing or changed reference record")

        def image_state(state):
            metadata = state["image"]
            asset = state.get("image_asset") or page.get("source_asset", "page.png")
            if asset_hashes.get(asset) != metadata.get("canonical_sha256"):
                raise ValueError("Page image hash mismatch")
            with Image.open(staged / asset) as image:
                if list(image.size) != [metadata["width"], metadata["height"]]:
                    raise ValueError("Page image dimensions do not match its coordinates")
            for region in state.get("regions", []):
                validate_box(region["box"], metadata["width"], metadata["height"])

        image_state(page)
        for old in image_states[1:]:
            image_state(old)
        if page.get("source_image"):
            source = page.get("source_asset", "page.png")
            if asset_hashes.get(source) != page["source_image"]["canonical_sha256"]:
                raise ValueError("Preserved source image hash mismatch")
        original = page.get("original_asset", "original.bin")
        if asset_hashes.get(original) != page["image"].get("original_sha256"):
            raise ValueError("Original image hash mismatch")
        if (staged / original).stat().st_size > MAX_BYTES:
            raise ValueError("Original upload exceeds 12 MiB")
        with Image.open(staged / original) as image:
            if (
                list(image.size) != page["image"]["original_size"]
                or image.getexif().get(274, 1) != page["image"]["exif_orientation"]
            ):
                raise ValueError("Original image orientation/size provenance mismatch")
    expected = set(asset_names(raw))
    if expected != set(asset_hashes):
        raise ValueError("Backup has missing or unreferenced image assets")
    # Choices remain exact, version-bound references; stale ones fail resolution
    # rather than being redirected to a different sample on import.
    if not isinstance(raw.get("sample_choices", {}), dict) or not isinstance(
        raw.get("selection_required", {}), dict
    ):
        raise ValueError("Invalid sample choice state")
    for label, chosen in raw.get("sample_choices", {}).items():
        RegionInput.valid_label(label)
        if (
            len(label) > 32
            or not label
            or not isinstance(chosen, dict)
            or set(chosen) != {"page_id", "region_id", "revision", "vector_sha256"}
            or chosen["page_id"] not in page_ids
            or type(chosen["revision"]) is not int
            or chosen["revision"] < 1
            or not isinstance(chosen["vector_sha256"], str)
            or not re.fullmatch("[a-f0-9]{64}", chosen["vector_sha256"])
        ):
            raise ValueError("Invalid exact sample-choice reference")
        uuid.UUID(chosen["region_id"])
    for label, reason in raw.get("selection_required", {}).items():
        RegionInput.valid_label(label)
        if not label or len(label) > 32 or not isinstance(reason, str) or len(reason) > 500:
            raise ValueError("Invalid sample-selection reminder")
    return raw


def import_backup(store, payload):
    if len(payload) > MAX_ARCHIVE:
        raise ValueError("Backup exceeds 256 MiB")
    with operation():
        directory_count(payload)
        project_id = uuid.uuid4().hex
        stage_root = store.root / ".staging"
        stage_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="import-", dir=stage_root) as temporary:
            staged = Path(temporary) / project_id
            staged.mkdir()
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                names, folded, total = set(), set(), 0
                for item in archive.infolist():
                    name = item.orig_filename
                    mode = stat.S_IFMT(item.external_attr >> 16)
                    if (
                        name in names
                        or name.casefold() in folded
                        or "\x00" in name
                        or "\\" in name
                        or name.startswith("/")
                        or any(p in {"", ".", ".."} for p in name.split("/"))
                    ):
                        raise ValueError("Unsafe, duplicate or case-colliding backup path")
                    if (
                        item.flag_bits & 1
                        or item.is_dir()
                        or mode not in {0, stat.S_IFREG}
                        or item.compress_type not in {0, 8}
                    ):
                        raise ValueError("Encrypted, linked or unsupported backup member")
                    if item.file_size > MAX_ASSET:
                        raise ValueError("Backup member is too large")
                    total += item.file_size
                    if total > MAX_TOTAL:
                        raise ValueError("Expanded backup exceeds 512 MiB")
                    names.add(name)
                    folded.add(name.casefold())
                manifest = json_data(read_member(archive, "manifest.json", MAX_DOCUMENT))
                if (
                    manifest.get("format") != "mashi-editable-project"
                    or type(manifest.get("version")) is not int
                    or manifest.get("version") != 1
                    or manifest.get("source_images_included") is not True
                    or manifest.get("model_weights_included") is not False
                ):
                    raise ValueError("Unsupported project backup format")
                expected = {"manifest.json", "project.json"}
                hashes = {}
                for record in manifest["assets"]:
                    name = safe_name(record["name"])
                    if name in hashes:
                        raise ValueError("Duplicate backup asset manifest")
                    member = "assets/" + name
                    data = read_member(archive, member)
                    if len(data) != record["bytes"] or sha(data) != record["sha256"]:
                        raise ValueError("Backup image hash/length mismatch")
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", Image.DecompressionBombWarning)
                        with Image.open(io.BytesIO(data)) as image:
                            if (
                                image.format not in {"JPEG", "PNG", "WEBP"}
                                or image.width * image.height > MAX_PIXELS
                                or name.endswith(".png")
                                and image.format != "PNG"
                            ):
                                raise ValueError("Invalid or oversized backup raster")
                            image.load()
                    (staged / name).write_bytes(data)
                    hashes[name] = sha(data)
                    expected.add(member)
                notices = {p.name: p.read_bytes() for p in LICENSE_ROOT.iterdir() if p.is_file()}
                seen_notices = set()
                for record in manifest["notices"]:
                    name = record["name"]
                    if name not in notices or name in seen_notices:
                        raise ValueError("Unknown or duplicate source notice")
                    data = read_member(archive, "notices/" + name)
                    if (
                        data != notices[name]
                        or sha(data) != record["sha256"]
                        or len(data) != record["bytes"]
                    ):
                        raise ValueError("Changed source notices in backup")
                    seen_notices.add(name)
                    expected.add("notices/" + name)
                if seen_notices != notices.keys() or names != expected:
                    raise ValueError("Backup contains unexpected or missing files")
                data = read_member(archive, "project.json", MAX_DOCUMENT)
                if sha(data) != manifest["project_sha256"]:
                    raise ValueError("Project data hash mismatch")
                project = json_data(data)
                raw = validate_project(project, staged, hashes)
            origin = raw["id"]
            raw["id"] = project_id
            raw.setdefault("project_history", []).append(
                {
                    "operation": "import-editable-backup",
                    "origin_project_id": origin,
                    "archive_sha256": sha(payload),
                    "at": time.time(),
                }
            )
            raw.pop("migration", None)  # The source's recovery file is not a local path here.
            encoded = json.dumps(raw, allow_nan=False)
            if len(encoded.encode()) > MAX_DOCUMENT:
                raise ValueError("Imported project data exceeds 16 MiB")
            final = store.root / project_id
            if final.exists() or final.is_symlink():
                raise ValueError("Import identity already exists; retry")
            published = False
            try:
                with store.connect() as db:
                    db.execute("BEGIN IMMEDIATE")
                    if os.name == "posix":
                        for asset in staged.iterdir():
                            with asset.open("rb") as stream:
                                os.fsync(stream.fileno())
                        descriptor = os.open(staged, os.O_RDONLY)
                        try:
                            os.fsync(descriptor)
                        finally:
                            os.close(descriptor)
                    os.replace(staged, final)
                    published = True
                    if os.name == "posix":
                        descriptor = os.open(store.root, os.O_RDONLY)
                        try:
                            os.fsync(descriptor)
                        finally:
                            os.close(descriptor)
                    db.execute("INSERT INTO projects VALUES (?, ?)", (project_id, encoded))
            except Exception:
                if published:
                    shutil.rmtree(final)
                raise
            return view(raw)
