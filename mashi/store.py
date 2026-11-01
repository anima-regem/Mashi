import json
import sqlite3
import uuid
import re
import zipfile
from pathlib import Path
from .projects import document, schema, view, request_page, invalidate_choices, MAX_DOCUMENT


def uid():
    return uuid.uuid4().hex


class Store:
    """JSON document per project, atomic optimistic revisions, append-only audit events."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, doc TEXT)")

    def connect(self):
        return sqlite3.connect(self.root / "mashi.sqlite3")

    def create(self, project):
        raw = document(project)
        with self.connect() as db:
            db.execute(
                "INSERT INTO projects VALUES (?, ?)",
                (project["id"], json.dumps(raw, allow_nan=False)),
            )
        project.clear()
        project.update(view(raw))

    def raw_text(self, project_id):
        with self.connect() as db:
            row = db.execute("SELECT doc FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError("Project not found")
        return row[0]

    def get(self, project_id, page_id=None):
        raw = json.loads(self.raw_text(project_id))
        selected, require = request_page.get()
        return view(
            raw, page_id or selected, require_page=require, migration_pending=schema(raw) == 1
        )

    def save(self, project):
        old_revision = project["revision"]
        old_text = self.raw_text(project["id"])
        before = json.loads(old_text)
        if before["revision"] != old_revision:
            raise ValueError("Project changed in another window; reload and try again")
        raw = document(project)
        previous = document(before)
        invalidate_choices(previous, raw)
        for page in raw["pages"]:
            old = next((p for p in previous["pages"] if p["id"] == page["id"]), None)
            if old is not None and page != old:
                page["revision"] = old["revision"] + 1
        raw["revision"] = old_revision + 1
        if schema(before) == 1:
            # Durable exact legacy document+assets before the first v2 write.
            from .backups import migration_backup

            try:
                raw["migration"] = migration_backup(self, before, old_text.encode())
            except (OSError, zipfile.BadZipFile) as error:
                raise ValueError(
                    "Could not create a verified recovery backup. No project migration was saved."
                ) from error
        encoded = json.dumps(raw, allow_nan=False)
        if len(encoded.encode()) > MAX_DOCUMENT:
            raise ValueError("Project data is too large; use fewer pages or samples")
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE projects SET doc=? WHERE id=? AND doc=?",
                (encoded, project["id"], old_text),
            )
            if cursor.rowcount != 1:
                raise ValueError("Project changed in another window; reload and try again")
        selected = project.get("page_id")
        project.clear()
        project.update(view(raw, selected))

    def list(self):
        with self.connect() as db:
            return [
                view(json.loads(row[0]), migration_pending=schema(json.loads(row[0])) == 1)
                for row in db.execute("SELECT doc FROM projects ORDER BY rowid DESC")
            ]

    def asset(self, project_id, filename):
        # IDs come from the database; filenames are internal constants.
        project_id = uuid.UUID(project_id).hex
        directory = self.root / project_id
        if (
            not isinstance(filename, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,159}", filename)
            or filename in {".", ".."}
        ):
            raise ValueError("Invalid project asset name")
        return directory / filename


def new_region(
    box, *, parents=None, label="", suggestion=None, source="manual", provenance="observed"
):
    return {
        "id": uid(),
        "box": list(box),
        "label": label,
        "confirmed": False,
        "suggestion": suggestion,
        "source": source,
        "provenance": provenance,
        "parents": parents or [],
        "revision": 1,
        "active": True,
        "vector": None,
    }
