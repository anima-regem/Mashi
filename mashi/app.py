import os
import secrets
import time
import io
import base64
import hashlib
import json
import zipfile
from statistics import median
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool

from . import ocr
from .exporting import export_bundle, export_preflight, preview_project, eligible
from .font_metrics import TypographyOptions
from .proofing import PreviewCache, bounded_diagnostics
from .ml_capture import aligned_reference, references_current, pixel_boundaries
from .ml_service import CompletionService, decode_prediction, source_terms, LICENSE_ROOT
from .imaging import MAX_BYTES, decode, propose_regions, validate_box
from .models import (
    MergeInput,
    RegionEdit,
    RegionCreateInput,
    SplitInput,
    TraceInput,
    VectorInput,
    PreparationInput,
    PreparationOptions,
    ProjectNameInput,
    RevisionInput,
    RegionRestoreInput,
    ProofInput,
    CompletionJob,
    CompletionReferences,
    CompletionGenerate,
    CompletionReview,
    CompletionVector,
    SampleChoiceInput,
    SavedTypographyInput,
)
from .projects import (
    pages,
    samples,
    signature,
    request_page,
    MAX_PAGES,
    font_is_synthetic,
    document,
)
from .backups import export_backup, import_backup, MAX_ARCHIVE
from .preparation import prepare, source_polygons, suggest_corners
from .predictors import coverage
from .store import Store, new_region, uid
from .tracing import svg, trace, validate_paths


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        path = scope["path"]
        limit = (
            MAX_ARCHIVE
            if path == "/api/projects/import"
            else MAX_BYTES
            if path == "/api/projects" or path.endswith("/pages")
            else 2_000_000
        )
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "Invalid content length"}, status_code=400)(
                scope, receive, send
            )
        if length > limit:
            return await JSONResponse({"detail": "Request too large"}, status_code=413)(
                scope, receive, send
            )
        total = 0

        async def bounded_receive():
            nonlocal total
            message = await receive()
            total += len(message.get("body", b""))
            if total > limit:
                raise HTTPException(413, "Request too large")
            return message

        await self.app(scope, bounded_receive, send)


def create_app(root=None, *, testing=False):
    app = FastAPI(title="Mashi", docs_url=None, redoc_url=None, openapi_url=None)
    store = Store(Path(root or os.environ.get("MASHI_DATA_DIR", ".mashi")))
    app.state.store = store
    previews = PreviewCache()
    app.state.previews = previews
    completion = CompletionService()
    app.state.completion = completion
    app.add_event_handler("shutdown", completion.unload)
    token = secrets.token_urlsafe(32)
    app.add_middleware(BodyLimit)
    hosts = ["localhost", "127.0.0.1"] + (["testserver"] if testing else [])
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    @app.middleware("http")
    async def local_requests(request, call_next):
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme != "http" or parsed.netloc != request.headers.get("host"):
                return JSONResponse(
                    {"detail": "Cross-origin requests are disabled"}, status_code=403
                )
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            if not secrets.compare_digest(request.headers.get("x-mashi-token", ""), token):
                return JSONResponse(
                    {"detail": "Reload Mashi before making changes"}, status_code=403
                )
        parts = request.url.path.split("/")
        page_scopes = {
            "image",
            "source-image",
            "regions",
            "preparation",
            "ocr",
            "merge",
            "completion",
        }
        context = request_page.set(
            (request.query_params.get("page_id"), len(parts) > 4 and parts[4] in page_scopes)
        )
        try:
            response = await call_next(request)
        finally:
            request_page.reset(context)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' blob: data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            }
        )
        return response

    @app.exception_handler(ValueError)
    async def bad_request(request, error):
        return JSONResponse({"detail": str(error)}, status_code=400)

    @app.exception_handler(KeyError)
    async def not_found(request, error):
        return JSONResponse({"detail": "Project or region not found"}, status_code=404)

    def project(project_id):
        return store.get(project_id)

    def region(doc, region_id, revision=None):
        result = next((r for r in doc["regions"] if r["id"] == region_id and r["active"]), None)
        if not result:
            raise KeyError(region_id)
        if revision is not None and result["revision"] != revision:
            raise HTTPException(409, "Crop changed; reload before editing")
        return result

    def input_provenance(doc):
        return "synthetic-fixture" if doc.get("source_kind") == "synthetic-fixture" else "observed"

    def make_region(doc, box, **kwargs):
        kwargs.setdefault("provenance", input_provenance(doc))
        item = new_region(box, **kwargs)
        item.update(source_polygons(box, doc["image"]))
        return item

    def image_path(doc, source=False):
        asset = (
            (doc.get("source_asset") if source else None) or doc.get("image_asset") or "page.png"
        )
        return store.asset(doc["id"], asset)

    def check_revision(doc, revision):
        if doc["revision"] != revision:
            raise HTTPException(
                409, "Page changed in another window; reload before applying changes"
            )

    def proposals_for(doc, image):
        try:
            boxes = propose_regions(image)
            doc.pop("capture_notice", None)
            return boxes
        except ValueError as error:
            doc["capture_notice"] = str(error) + ". Prepare the photo or draw crops manually."
            return []

    def event(doc, operation, ids):
        doc["history"].append(
            {
                "operation": operation,
                "regions": ids,
                "at": time.time(),
                "project_revision": doc["revision"] + 1,
            }
        )
        store.save(doc)
        return doc

    def project_event(doc, operation):
        doc.setdefault("project_history", []).append(
            {"operation": operation, "at": time.time(), "project_revision": doc["revision"] + 1}
        )
        store.save(doc)
        return doc

    @app.get("/api/session")
    def session():
        return {
            "token": token,
            "ocr": ocr.capabilities(),
            "version": "0.1.0",
            "features": {"multi_page": True, "editable_backup": True},
        }

    @app.get("/api/projects")
    def projects():
        return [
            {
                "id": p["id"],
                "created": p["created"],
                "image": p["image"],
                "name": p.get("name", "Untitled page"),
                "page_count": len(p["pages"]),
            }
            for p in store.list()
        ]

    @app.post("/api/projects")
    async def upload(
        request: Request, source: Literal["user-upload", "synthetic-fixture"] = "user-upload"
    ):
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BYTES:
                raise HTTPException(413, "Image exceeds 12 MiB")
            chunks.append(chunk)
        data = b"".join(chunks)
        image, canonical, metadata = decode(data)
        doc = {
            "id": uid(),
            "revision": 1,
            "created": time.time(),
            "source_kind": source,
            "name": "Practice font" if source == "synthetic-fixture" else "Untitled font",
            "image": metadata,
            "regions": [],
            "history": [{"operation": "upload", "at": time.time()}],
        }
        doc["regions"] = [
            make_region(doc, box, source="connected-ink-proposal")
            for box in proposals_for(doc, image)
        ]
        (store.root / doc["id"]).mkdir()
        store.asset(doc["id"], "original.bin").write_bytes(data)
        store.asset(doc["id"], "page.png").write_bytes(canonical)
        raw = document(doc)
        raw["pages"][0]["name"] = "Page 1"
        store.create(raw)
        return raw

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        return project(project_id)

    @app.post("/api/projects/import")
    async def restore_backup(request: Request):
        data, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_ARCHIVE:
                raise HTTPException(413, "Backup exceeds 256 MiB")
            data.append(chunk)
        try:
            return await run_in_threadpool(import_backup, store, b"".join(data))
        except (
            OSError,
            TypeError,
            KeyError,
            AttributeError,
            IndexError,
            zipfile.BadZipFile,
            OverflowError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as error:
            raise ValueError(
                "Invalid project backup. Your existing projects were not changed."
            ) from error

    @app.post("/api/projects/{project_id}/backup")
    def backup_project(project_id: str, data: RevisionInput):
        doc = project(project_id)
        check_revision(doc, data.revision)
        archive = export_backup(store, project_id)
        check_revision(project(project_id), data.revision)
        return Response(
            archive,
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="Mashi-Project.mashi.zip"'},
        )

    @app.post("/api/projects/{project_id}/pages")
    async def append_page(
        project_id: str,
        request: Request,
        revision: int,
        source: Literal["user-upload", "synthetic-fixture"] = "user-upload",
    ):
        doc = project(project_id)
        check_revision(doc, revision)
        if len(doc["pages"]) >= MAX_PAGES:
            raise ValueError("A font project can contain up to 20 pages")
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BYTES:
                raise HTTPException(413, "Image exceeds 12 MiB")
            chunks.append(chunk)
        data = b"".join(chunks)
        image, canonical, metadata = decode(data)
        page_id = uid()
        page = {
            "id": page_id,
            "name": f"Page {len(doc['pages']) + 1}",
            "revision": 1,
            "source_kind": source,
            "image": metadata,
            "regions": [],
            "history": [{"operation": "upload", "at": time.time()}],
            "original_asset": f"p-{page_id}-original.bin",
            "image_asset": f"p-{page_id}.png",
        }
        page["regions"] = [
            make_region(page, box, source="connected-ink-proposal")
            for box in proposals_for(page, image)
        ]
        store.asset(project_id, page["original_asset"]).write_bytes(data)
        store.asset(project_id, page["image_asset"]).write_bytes(canonical)
        doc["pages"].append(page)
        project_event(doc, "add-page")
        return store.get(project_id, page_id)

    @app.put("/api/projects/{project_id}/pages/{page_id}/name")
    def rename_page(project_id: str, page_id: str, data: ProjectNameInput):
        doc = store.get(project_id, page_id)
        check_revision(doc, data.revision)
        doc["page_name"] = data.name
        return event(doc, "rename-page", [])

    @app.put("/api/projects/{project_id}/samples/select")
    def select_sample(project_id: str, data: SampleChoiceInput):
        doc = project(project_id)
        check_revision(doc, data.revision)
        found = next(
            (
                (page, row)
                for page, row, _, _ in samples(doc)
                if page["id"] == data.page_id
                and row["id"] == data.region_id
                and row["label"] == data.label
                and row["revision"] == data.sample_revision
            ),
            None,
        )
        if not found:
            raise HTTPException(409, "That sample changed. Reload before choosing it.")
        doc.setdefault("sample_choices", {})[data.label] = signature(*found)
        doc.setdefault("selection_required", {}).pop(data.label, None)
        return project_event(doc, "choose-font-sample")

    @app.put("/api/projects/{project_id}/typography")
    def save_typography(project_id: str, data: SavedTypographyInput):
        doc = project(project_id)
        check_revision(doc, data.revision)
        TypographyOptions(**data.options.model_dump()).validate()
        if data.text.count("\n") >= 32:
            raise ValueError("Use at most 32 proof lines")
        doc["typography"] = data.options.model_dump()
        doc["proof_text"] = data.text
        doc["typography_revision"] = doc.get("typography_revision", 1) + 1
        return project_event(doc, "save-font-settings")

    @app.get("/api/projects/{project_id}/image")
    def image(project_id: str, expected_sha256: str | None = None):
        doc = project(project_id)
        if expected_sha256 is not None and expected_sha256 != doc["image"]["canonical_sha256"]:
            raise HTTPException(409, "Page pixels changed; reload the saved page")
        return FileResponse(image_path(doc), media_type="image/png")

    @app.get("/api/projects/{project_id}/source-image")
    def source_image(project_id: str):
        return FileResponse(image_path(project(project_id), source=True), media_type="image/png")

    @app.put("/api/projects/{project_id}/name")
    def name_project(project_id: str, data: ProjectNameInput):
        doc = project(project_id)
        check_revision(doc, data.revision)
        doc["name"] = data.name
        return project_event(doc, "rename-font-project")

    @app.post("/api/projects/{project_id}/preparation/suggest")
    def suggest_preparation(project_id: str):
        with Image.open(image_path(project(project_id), source=True)) as source:
            return suggest_corners(source.convert("RGB"))

    @app.post("/api/projects/{project_id}/preparation/preview")
    def preview_preparation(project_id: str, data: PreparationOptions):
        with Image.open(image_path(project(project_id), source=True)) as source:
            result, _, metadata = prepare(source, data)
        result.thumbnail((1000, 1000))
        encoded = io.BytesIO()
        result.save(encoded, "PNG")
        return Response(
            encoded.getvalue(),
            media_type="image/png",
            headers={
                "X-Prepared-Width": str(metadata["width"]),
                "X-Prepared-Height": str(metadata["height"]),
            },
        )

    @app.post("/api/projects/{project_id}/preparation")
    def apply_preparation(project_id: str, data: PreparationInput):
        doc = project(project_id)
        check_revision(doc, data.revision)
        if len(doc.get("preparation_history", [])) >= 20:
            raise ValueError(
                "This page has 20 preparation states. Restore a previous state or start another page."
            )
        doc.setdefault("source_asset", doc.get("image_asset", "page.png"))
        doc.setdefault("source_image", deepcopy(doc["image"]))
        options = PreparationOptions(**data.model_dump(exclude={"revision"}))
        with Image.open(image_path(doc, source=True)) as source:
            result, encoded, metadata = prepare(source, options)
        snapshot = {
            key: deepcopy(doc.get(key))
            for key in ["image", "regions", "image_asset", "preparation", "capture_notice"]
        }
        proposals = proposals_for(doc, result)
        doc.setdefault("preparation_history", []).append(snapshot)
        doc["image_asset"] = "prepared-" + uid() + ".png"
        store.asset(doc["id"], doc["image_asset"]).write_bytes(encoded)
        doc["image"] = {
            **deepcopy(doc["source_image"]),
            **metadata,
            "source_canonical_sha256": doc["source_image"]["canonical_sha256"],
            "preparation_revision": doc["revision"] + 1,
        }
        doc["image"]["transforms"].append({"operation": "page_preparation", **metadata})
        doc["preparation"] = options.model_dump()
        doc["regions"] = [
            make_region(doc, box, source="prepared-ink-proposal") for box in proposals
        ]
        return event(doc, "prepare-page-resegment-unconfirmed", [])

    @app.post("/api/projects/{project_id}/preparation/restore")
    def restore_preparation(project_id: str, data: RevisionInput):
        doc = project(project_id)
        check_revision(doc, data.revision)
        if not doc.get("preparation_history"):
            raise ValueError("No earlier preparation state to restore")
        snapshot = doc["preparation_history"].pop()
        for key, value in snapshot.items():
            if value is None:
                doc.pop(key, None)
            else:
                doc[key] = value
        return event(doc, "restore-preparation-and-crops", [])

    @app.post("/api/projects/{project_id}/regions")
    def add_region(project_id: str, data: RegionCreateInput):
        doc = project(project_id)
        check_revision(doc, data.project_revision)
        if len(doc["regions"]) >= 5000:
            raise ValueError("Project region limit reached; start a new page")
        validate_box(data.box, doc["image"]["width"], doc["image"]["height"])
        if data.confirmed and not data.label:
            raise ValueError("Assign a label before confirming")
        item = make_region(doc, data.box, label=data.label)
        item["confirmed"] = data.confirmed
        doc["regions"].append(item)
        return event(doc, "add", [item["id"]])

    @app.put("/api/projects/{project_id}/regions/{region_id}")
    def edit_region(project_id: str, region_id: str, data: RegionEdit):
        doc = project(project_id)
        item = region(doc, region_id, data.revision)
        validate_box(data.box, doc["image"]["width"], doc["image"]["height"])
        if data.confirmed and not data.label:
            raise ValueError("Assign a label before confirming")
        doc["history"].append(
            {"operation": "before-edit", "snapshot": dict(item), "at": time.time()}
        )
        if list(data.box) != item["box"]:
            item["vector"] = None
        item.update(
            {
                "box": list(data.box),
                "label": data.label,
                "confirmed": data.confirmed,
                "revision": item["revision"] + 1,
            }
        )
        item.update(source_polygons(data.box, doc["image"]))
        return event(doc, "edit", [region_id])

    @app.post("/api/projects/{project_id}/regions/{region_id}/split")
    def split(project_id: str, region_id: str, data: SplitInput):
        doc = project(project_id)
        item = region(doc, region_id, data.revision)
        x0, y0, x1, y1 = item["box"]
        p = data.position
        if data.axis == "x" and x0 < p < x1:
            boxes = [(x0, y0, p, y1), (p, y0, x1, y1)]
        elif data.axis == "y" and y0 < p < y1:
            boxes = [(x0, y0, x1, p), (x0, p, x1, y1)]
        else:
            raise ValueError("Split position must be strictly inside the crop")
        item["active"] = False
        item["revision"] += 1
        children = [make_region(doc, b, parents=[region_id], source="split") for b in boxes]
        doc["regions"].extend(children)
        return event(doc, "split", [region_id] + [c["id"] for c in children])

    @app.delete("/api/projects/{project_id}/regions/{region_id}")
    def discard(project_id: str, region_id: str, revision: int):
        doc = project(project_id)
        item = region(doc, region_id, revision)
        item["active"] = False
        item["revision"] += 1
        return event(doc, "discard", [region_id])

    @app.post("/api/projects/{project_id}/merge")
    def merge(project_id: str, data: MergeInput):
        doc = project(project_id)
        if len(set(data.ids)) != len(data.ids) or len(data.ids) != len(data.revisions):
            raise ValueError("Choose distinct crops and their revisions")
        items = [region(doc, rid, rev) for rid, rev in zip(data.ids, data.revisions)]
        boxes = [r["box"] for r in items]
        merged = make_region(
            doc,
            [
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            ],
            parents=data.ids,
            source="merge",
            provenance=input_provenance(doc),
        )
        for item in items:
            item["active"] = False
            item["revision"] += 1
        doc["regions"].append(merged)
        return event(doc, "merge", data.ids + [merged["id"]])

    @app.post("/api/projects/{project_id}/ocr")
    def run_ocr(project_id: str, data: RevisionInput):
        doc = project(project_id)
        check_revision(doc, data.revision)
        if len(doc["regions"]) >= 4000:
            raise ValueError("Too many regions; use another project")
        suggestions = ocr.recognize(image_path(doc))
        for suggestion in suggestions:
            validate_box(suggestion["box"], doc["image"]["width"], doc["image"]["height"])
            doc["regions"].append(
                make_region(
                    doc,
                    suggestion["box"],
                    suggestion=suggestion,
                    source="ocr-word",
                    provenance=input_provenance(doc),
                )
            )
        return event(doc, "ocr-word-proposals", [])

    @app.post("/api/projects/{project_id}/regions/{region_id}/trace")
    def trace_region(project_id: str, region_id: str, data: TraceInput):
        doc = project(project_id)
        item = region(doc, region_id, data.revision)
        if item["vector"]:
            doc["history"].append(
                {"operation": "before-retrace", "snapshot": dict(item), "at": time.time()}
            )
        with Image.open(image_path(doc)) as page:
            item["vector"] = trace(page.crop(item["box"]), data.threshold)
        item["revision"] += 1
        return event(doc, "trace", [region_id])

    @app.put("/api/projects/{project_id}/regions/{region_id}/vector")
    def edit_vector(project_id: str, region_id: str, data: VectorInput):
        doc = project(project_id)
        item = region(doc, region_id, data.revision)
        if not item["vector"]:
            raise ValueError("Trace this crop first")
        validate_paths(data.paths)
        if not 0 <= data.baseline <= item["vector"]["height"]:
            raise ValueError("Baseline must be inside the crop")
        doc["history"].append(
            {"operation": "before-vector-edit", "snapshot": dict(item), "at": time.time()}
        )
        item["vector"] = {**item["vector"], **data.model_dump(exclude={"revision"}), "edited": True}
        item["revision"] += 1
        return event(doc, "vector-edit", [region_id])

    @app.get("/api/projects/{project_id}/regions/{region_id}/svg")
    def region_svg(project_id: str, region_id: str):
        item = region(project(project_id), region_id)
        if not item["vector"]:
            raise ValueError("Trace this crop first")
        return Response(
            svg(item["vector"], item["provenance"]),
            media_type="image/svg+xml",
            headers={
                "Content-Disposition": 'attachment; filename="mashi-synthetic-glyph.svg"'
                if item["provenance"] == "synthetic-fixture"
                else 'attachment; filename="mashi-glyph.svg"'
            },
        )

    def restorable(doc, region_id):
        return [
            (index, entry)
            for index, entry in enumerate(doc["history"])
            if entry.get("snapshot", {}).get("id") == region_id
            and entry["snapshot"].get("image_revision", 0)
            == doc["image"].get("preparation_revision", 0)
            and entry["snapshot"].get("provenance") == input_provenance(doc)
        ]

    @app.get("/api/projects/{project_id}/regions/{region_id}/history")
    def region_history(project_id: str, region_id: str):
        doc = project(project_id)
        region(doc, region_id)
        return [
            {
                "index": i,
                "operation": e["operation"],
                "at": e["at"],
                "revision": e["snapshot"]["revision"],
                "has_outline": bool(e["snapshot"].get("vector")),
            }
            for i, e in reversed(restorable(doc, region_id))
        ]

    @app.post("/api/projects/{project_id}/regions/{region_id}/restore")
    def restore_region(project_id: str, region_id: str, data: RegionRestoreInput):
        doc = project(project_id)
        item = region(doc, region_id, data.revision)
        snapshots = dict(restorable(doc, region_id))
        if data.history_index not in snapshots:
            raise ValueError("That saved state does not belong to this crop, image or provenance")
        restored = deepcopy(snapshots[data.history_index]["snapshot"])
        validate_box(restored["box"], doc["image"]["width"], doc["image"]["height"])
        if restored.get("vector"):
            validate_paths(restored["vector"]["paths"])
        doc["history"].append(
            {"operation": "before-restore", "snapshot": deepcopy(item), "at": time.time()}
        )
        restored.update({"revision": item["revision"] + 1, "active": True})
        restored.update(source_polygons(restored["box"], doc["image"]))
        doc["regions"][doc["regions"].index(item)] = restored
        return event(doc, "restore-saved-crop-outline", [region_id])

    @app.get("/api/projects/{project_id}/coverage")
    def get_coverage(project_id: str):
        return coverage(project(project_id))

    @app.get("/api/completion/capabilities")
    def completion_capabilities():
        return completion.capabilities()

    @app.post("/api/projects/{project_id}/completion/load")
    def completion_load(project_id: str, data: CompletionJob):
        check_revision(project(project_id), data.revision)
        result = completion.load(project_id, data.job_id)
        check_revision(project(project_id), data.revision)
        return result

    @app.post("/api/completion/unload")
    def completion_unload():
        completion.unload()
        return completion.capabilities()

    @app.post("/api/projects/{project_id}/completion/cancel")
    def completion_cancel(project_id: str, data: CompletionJob):
        completion.cancel(project_id, data.job_id)
        doc = project(project_id)
        changed = []
        for item in doc.get("completion_suggestions", []):
            if item["generation"]["job_id"] == data.job_id and item["review_state"] == "pending":
                item.update(review_state="rejected", canceled=True, revision=item["revision"] + 1)
                changed.append(item["id"])
        if changed:
            event(doc, "cancel-generated-suggestions", changed)
        return {"canceled": True}

    def completion_references(doc, ids):
        if completion.model is None:
            raise ValueError("Load the configured local checkpoint first")
        if len(set(ids)) != len(ids):
            raise ValueError("Choose distinct reference crops")
        results, labels = [], set()
        for rid in ids:
            item = region(doc, rid)
            allowed = item["provenance"] == "observed" or (
                doc.get("source_kind") == "synthetic-fixture"
                and item["provenance"] == "synthetic-fixture"
            )
            if (
                not allowed
                or not item["confirmed"]
                or not item.get("vector")
                or item["label"] not in completion.model["labels"]
                or item["label"] in labels
            ):
                raise ValueError(
                    "Choose one confirmed, traced, supported reference per exact sequence; generated forms cannot be references"
                )
            labels.add(item["label"])
            results.append(aligned_reference(item))
        return results

    @app.post("/api/projects/{project_id}/completion/references")
    def preview_completion_references(project_id: str, data: CompletionReferences):
        doc = project(project_id)
        check_revision(doc, data.revision)
        results = completion_references(doc, data.ids)
        check_revision(project(project_id), data.revision)
        return {"revision": data.revision, "references": results}

    def suggestion(doc, suggestion_id, revision=None):
        item = next(
            (r for r in doc.get("completion_suggestions", []) if r["id"] == suggestion_id), None
        )
        if item is None:
            raise KeyError(suggestion_id)
        if revision is not None and item["revision"] != revision:
            raise HTTPException(409, "Suggestion changed; reload before reviewing")
        return item

    @app.post("/api/projects/{project_id}/completion/generate")
    def generate_completion(project_id: str, data: CompletionGenerate):
        doc = project(project_id)
        check_revision(doc, data.revision)
        if len(doc.get("completion_suggestions", [])) + len(data.targets) > 200:
            raise ValueError("This page has 200 suggestions. Use manual capture or another page.")
        refs = completion_references(doc, data.ids)
        if not data.alignment_confirmed or data.reference_hashes != {
            r["id"]: r["sha256"] for r in refs
        }:
            raise ValueError(
                "Preview and confirm these exact reference alignments before generation"
            )
        present = {
            r["label"]
            for page in pages(doc)
            for r in page["regions"]
            if r["active"] and r["confirmed"]
        }
        present |= {
            r["label"]
            for page in pages(doc)
            for r in page.get("completion_suggestions", [])
            if r["review_state"] != "rejected"
        }
        if len(set(data.targets)) != len(data.targets) or any(
            t not in completion.model["labels"] or t in present for t in data.targets
        ):
            raise ValueError(
                "Request only unique, supported missing sequences. Review/reject an existing candidate before regenerating it."
            )
        result = completion.generate(project_id, data.job_id, refs, data.targets)
        check_revision(project(project_id), data.revision)
        if [s["label"] for s in result["suggestions"]] != data.targets or result["model"][
            "sha256"
        ] != completion.digest:
            raise ValueError("Completion output does not match the requested model/targets")
        observations = []
        for ref in refs:
            asset = f"reference-{uid()}.png"
            store.asset(project_id, asset).write_bytes(base64.b64decode(ref["png"], validate=True))
            observations.append({k: v for k, v in ref.items() if k != "png"} | {"asset": asset})
        generation = {
            "job_id": data.job_id,
            "project_id": project_id,
            "page_id": doc["page_id"],
            "project_revision": data.revision,
            "image_sha256": doc["image"]["canonical_sha256"],
            "model": result["model"],
            "observations": observations,
            "uncertainty": "uncalibrated",
            "method": "pca-or-mean; template inference and diagnostics disabled",
            "request_sha256": hashlib.sha256(
                json.dumps(data.model_dump(), sort_keys=True).encode()
            ).hexdigest(),
        }
        new = []
        for output in result["suggestions"]:
            payload = decode_prediction(output)
            sid = uid()
            asset = "generated-" + sid + ".png"
            store.asset(project_id, asset).write_bytes(payload)
            vector = None
            error = ""
            ink_box = [0, 0, 96, 64]
            try:
                with Image.open(io.BytesIO(payload)) as image:
                    if image.size != (96, 64):
                        raise ValueError("Generated canvas has unexpected dimensions")
                    bounds = (
                        image.convert("L").point(lambda value: 255 if value < 180 else 0).getbbox()
                    )
                    if bounds is None:
                        raise ValueError("Prediction has no ink")
                    ink_box = list(bounds)
                    cropped = image.crop(bounds)
                    try:
                        vector = trace(cropped.convert("RGB"), 180)
                    except ValueError:
                        vector = pixel_boundaries(cropped, 180)
                vector.update(
                    baseline=45 - ink_box[1],
                    scale=1000 / 32,
                    advance=max(
                        100.0,
                        min(
                            5000.0,
                            max(
                                float(median(r["advance"] for r in refs)),
                                vector["width"] * 31.25 + 100,
                            ),
                        ),
                    ),
                )
            except ValueError as exception:
                error = str(exception)
            item = {
                "id": sid,
                "label": output["label"],
                "revision": 1,
                "active": True,
                "confirmed": False,
                "review_state": "pending",
                "provenance": "model-generated",
                "not_observed_in_photo": True,
                "coordinate_space": "generated-canvas",
                "box": ink_box,
                "raster_asset": asset,
                "raster_sha256": output["sha256"],
                "empty_prediction": output["empty"],
                "trace_error": error,
                "vector": vector,
                "generation": deepcopy(generation),
                "history": [],
                "vectorization": {
                    "method": vector["tracer"] if vector else "failed",
                    "threshold": 180,
                    "canvas": [96, 64],
                    "canonical_to_vector": [[1, 0, -ink_box[0]], [0, 1, -ink_box[1]], [0, 0, 1]],
                    "ink_box": ink_box,
                    "left_bearing_estimate": 50,
                },
            }
            item["generation"].update(
                target_sequence=output["label"],
                raster_sha256=output["sha256"],
                vectorization=deepcopy(item["vectorization"]),
            )
            new.append(item)
        with completion.guard:
            if (project_id, data.job_id) in completion.canceled:
                raise ValueError("Completion request canceled")
            doc.setdefault("completion_suggestions", []).extend(new)
            return event(doc, "model-generated-proposals", [r["id"] for r in new])

    @app.get("/api/projects/{project_id}/completion/suggestions/{suggestion_id}/raster")
    def suggestion_raster(project_id: str, suggestion_id: str):
        item = suggestion(project(project_id), suggestion_id)
        return FileResponse(store.asset(project_id, item["raster_asset"]), media_type="image/png")

    @app.get(
        "/api/projects/{project_id}/completion/suggestions/{suggestion_id}/reference/{reference_id}"
    )
    def suggestion_reference(project_id: str, suggestion_id: str, reference_id: str):
        item = suggestion(project(project_id), suggestion_id)
        ref = next((r for r in item["generation"]["observations"] if r["id"] == reference_id), None)
        if not ref:
            raise KeyError(reference_id)
        return FileResponse(store.asset(project_id, ref["asset"]), media_type="image/png")

    @app.get("/api/projects/{project_id}/completion/suggestions/{suggestion_id}/svg")
    def suggestion_svg(project_id: str, suggestion_id: str):
        doc = project(project_id)
        item = suggestion(doc, suggestion_id)
        terms = source_terms(item["generation"]["model"]["sha256"])
        if (
            not item["vector"]
            or item["review_state"] != "accepted"
            or not terms["checkpoint_source_known"]
            or not references_current(doc, item)
        ):
            raise ValueError(
                "Accept a usable suggestion with known source terms before downloading generated geometry"
            )
        metadata = deepcopy(item["generation"])
        metadata["vector_edited"] = item["vector"]["edited"]
        metadata["source_license_texts"] = {
            record["notice"]: (LICENSE_ROOT / record["notice"]).read_text(encoding="utf-8-sig")
            for record in terms["notices"]
        }
        metadata["output_license"] = (LICENSE_ROOT / "OFL.txt").read_text()
        return Response(
            svg(item["vector"], "model-generated", generation=metadata),
            media_type="image/svg+xml",
        )

    @app.post("/api/projects/{project_id}/completion/suggestions/{suggestion_id}/review")
    def review_completion(project_id: str, suggestion_id: str, data: CompletionReview):
        doc = project(project_id)
        check_revision(doc, data.revision)
        item = suggestion(doc, suggestion_id, data.suggestion_revision)
        if data.state == "accepted" and (
            item["empty_prediction"] or not item["vector"] or not references_current(doc, item)
        ):
            raise ValueError(
                "Empty, untraced or stale-reference proposals cannot be accepted. Capture the form or generate again."
            )
        item["history"].append(
            {"state": item["review_state"], "revision": item["revision"], "at": time.time()}
        )
        item.update(
            review_state=data.state,
            confirmed=data.state == "accepted",
            revision=item["revision"] + 1,
        )
        return event(doc, "review-generated-" + data.state, [suggestion_id])

    @app.put("/api/projects/{project_id}/completion/suggestions/{suggestion_id}/vector")
    def edit_completion_vector(project_id: str, suggestion_id: str, data: CompletionVector):
        doc = project(project_id)
        check_revision(doc, data.project_revision)
        item = suggestion(doc, suggestion_id, data.revision)
        if not item["vector"]:
            raise ValueError("This suggestion has no usable outline; capture the form manually")
        validate_paths(data.paths)
        item["history"].append(
            {
                "state": item["review_state"],
                "vector": deepcopy(item["vector"]),
                "revision": item["revision"],
                "at": time.time(),
            }
        )
        item["vector"].update(
            paths=data.paths,
            baseline=data.baseline,
            scale=data.scale,
            advance=data.advance,
            edited=True,
        )
        item.update(review_state="pending", confirmed=False, revision=item["revision"] + 1)
        return event(doc, "edit-generated-outline-review-again", [suggestion_id])

    @app.post("/api/projects/{project_id}/proof/{action}")
    def proof(
        project_id: str,
        action: Literal["preflight", "preview"],
        data: ProofInput,
        include_fixture: bool = False,
        include_generated: bool = False,
    ):
        doc = project(project_id)
        check_revision(doc, data.revision)
        options = TypographyOptions(
            **(
                data.options.model_dump()
                if "options" in data.model_fields_set
                else doc.get("typography", {})
            )
        )
        options.validate()
        if action == "preflight":
            result = {
                "coverage": bounded_diagnostics(
                    export_preflight(
                        doc, data.text, include_fixture, include_generated=include_generated
                    ),
                    "issues",
                )
            }
        else:
            result = previews.get(
                doc,
                data.text,
                options,
                include_fixture,
                lambda: preview_project(
                    doc,
                    data.text,
                    include_fixture,
                    options=options,
                    include_generated=include_generated,
                ),
                include_generated=include_generated,
            )
        check_revision(project(project_id), data.revision)
        return {**result, "project_id": project_id, "revision": data.revision}

    @app.post("/api/projects/{project_id}/export/{kind}")
    def export(
        project_id: str,
        kind: str,
        include_fixture: bool = False,
        data: ProofInput | None = None,
        include_generated: bool = False,
    ):
        if kind not in {"ufo", "ttf"}:
            raise ValueError("Choose ufo or ttf")
        doc = project(project_id)
        if include_generated and data is None:
            raise ValueError(
                "Generated fonts require an explicit proof body and generated-output choice"
            )
        if data is not None:
            check_revision(doc, data.revision)
        archive = export_bundle(
            doc,
            kind,
            include_fixture=include_fixture,
            options=TypographyOptions(
                **(
                    data.options.model_dump()
                    if "options" in data.model_fields_set
                    else doc.get("typography", {})
                )
            )
            if data
            else TypographyOptions(**doc.get("typography", {})),
            required_text=data.text if data else doc.get("proof_text") or None,
            include_generated=include_generated,
        )
        check_revision(project(project_id), doc["revision"])
        prefix = (
            "Mashi-SYNTHETIC"
            if font_is_synthetic(
                doc, eligible(doc, include_fixture, include_generated=include_generated)
            )
            else "Mashi"
        )
        if include_generated:
            prefix += "-GENERATED"
        return Response(
            archive,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{prefix}-{kind}.zip"'},
        )

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    return app


app = create_app()
