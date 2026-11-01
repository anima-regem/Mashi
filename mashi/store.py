import json
import sqlite3
import uuid
from pathlib import Path


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
        with self.connect() as db:
            db.execute("INSERT INTO projects VALUES (?, ?)", (project["id"], json.dumps(project)))

    def get(self, project_id):
        with self.connect() as db:
            row = db.execute("SELECT doc FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError("Project not found")
        return json.loads(row[0])

    def save(self, project):
        old_revision = project["revision"]
        project["revision"] += 1
        with self.connect() as db:
            cursor = db.execute(
                "UPDATE projects SET doc=? WHERE id=? AND json_extract(doc, '$.revision')=?",
                (json.dumps(project), project["id"], old_revision),
            )
            if cursor.rowcount != 1:
                raise ValueError("Project changed in another window; reload and try again")

    def list(self):
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute("SELECT doc FROM projects ORDER BY rowid DESC")
            ]

    def asset(self, project_id, filename):
        # IDs come from the database; filenames are internal constants.
        project_id = uuid.UUID(project_id).hex
        directory = self.root / project_id
        directory.mkdir(exist_ok=True)
        return directory / filename


def new_region(box, *, parents=None, label="", suggestion=None, source="manual"):
    return {
        "id": uid(),
        "box": list(box),
        "label": label,
        "confirmed": False,
        "suggestion": suggestion,
        "source": source,
        "provenance": "observed",
        "parents": parents or [],
        "revision": 1,
        "active": True,
        "vector": None,
    }
