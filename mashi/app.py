import os
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import ocr
from .exporting import export_bundle
from .imaging import MAX_BYTES, decode, propose_regions, validate_box
from .models import MergeInput, RegionEdit, RegionInput, SplitInput, TraceInput, VectorInput
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
        limit = MAX_BYTES if scope["path"] == "/api/projects" else 2_000_000
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
        response = await call_next(request)
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

    @app.get("/api/session")
    def session():
        return {"token": token, "ocr": ocr.capabilities(), "version": "0.1.0"}

    @app.get("/api/projects")
    def projects():
        return [{"id": p["id"], "created": p["created"], "image": p["image"]} for p in store.list()]

    @app.post("/api/projects")
    async def upload(request: Request):
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
            "image": metadata,
            "regions": [
                new_region(box, source="connected-ink-proposal") for box in propose_regions(image)
            ],
            "history": [{"operation": "upload", "at": time.time()}],
        }
        store.asset(doc["id"], "original.bin").write_bytes(data)
        store.asset(doc["id"], "page.png").write_bytes(canonical)
        store.create(doc)
        return doc

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        return project(project_id)

    @app.get("/api/projects/{project_id}/image")
    def image(project_id: str):
        project(project_id)
        return FileResponse(store.asset(project_id, "page.png"), media_type="image/png")

    @app.post("/api/projects/{project_id}/regions")
    def add_region(project_id: str, data: RegionInput):
        doc = project(project_id)
        if len(doc["regions"]) >= 5000:
            raise ValueError("Project region limit reached; start a new page")
        validate_box(data.box, doc["image"]["width"], doc["image"]["height"])
        if data.confirmed and not data.label:
            raise ValueError("Assign a label before confirming")
        item = new_region(data.box, label=data.label)
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
        children = [new_region(b, parents=[region_id], source="split") for b in boxes]
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
        merged = new_region(
            [
                min(b[0] for b in boxes),
                min(b[1] for b in boxes),
                max(b[2] for b in boxes),
                max(b[3] for b in boxes),
            ],
            parents=data.ids,
            source="merge",
        )
        for item in items:
            item["active"] = False
            item["revision"] += 1
        doc["regions"].append(merged)
        return event(doc, "merge", data.ids + [merged["id"]])

    @app.post("/api/projects/{project_id}/ocr")
    def run_ocr(project_id: str):
        doc = project(project_id)
        if len(doc["regions"]) >= 4000:
            raise ValueError("Too many regions; use another project")
        suggestions = ocr.recognize(store.asset(project_id, "page.png"))
        for suggestion in suggestions:
            validate_box(suggestion["box"], doc["image"]["width"], doc["image"]["height"])
            doc["regions"].append(
                new_region(suggestion["box"], suggestion=suggestion, source="ocr-word")
            )
        return event(doc, "ocr-word-proposals", [])

    @app.post("/api/projects/{project_id}/regions/{region_id}/trace")
    def trace_region(project_id: str, region_id: str, data: TraceInput):
        doc = project(project_id)
        item = region(doc, region_id, data.revision)
        with Image.open(store.asset(project_id, "page.png")) as page:
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
            svg(item["vector"]),
            media_type="image/svg+xml",
            headers={"Content-Disposition": 'attachment; filename="mashi-glyph.svg"'},
        )

    @app.get("/api/projects/{project_id}/coverage")
    def get_coverage(project_id: str):
        return coverage(project(project_id))

    @app.post("/api/projects/{project_id}/export/{kind}")
    def export(project_id: str, kind: str):
        if kind not in {"ufo", "ttf"}:
            raise ValueError("Choose ufo or ttf")
        return Response(
            export_bundle(project(project_id), kind),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="Mashi-{kind}.zip"'},
        )

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/")
    def index():
        return FileResponse(static / "index.html")

    return app


app = create_app()
