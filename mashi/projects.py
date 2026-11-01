"""Versioned font projects, page views and one shared exact-sequence resolver."""

from collections import defaultdict
from contextvars import ContextVar
from copy import deepcopy
import hashlib
import json

SCHEMA = 2
MAX_PAGES = 20
MAX_DOCUMENT = 16 * 1024 * 1024
PAGE_KEYS = {
    "image",
    "source_image",
    "source_kind",
    "image_asset",
    "source_asset",
    "original_asset",
    "regions",
    "history",
    "preparation",
    "preparation_history",
    "capture_notice",
    "completion_suggestions",
}
VIEW_KEYS = {
    "page_id",
    "page_name",
    "page_revision",
    "sample_groups",
    "has_synthetic_pages",
    "migration_pending",
}
request_page = ContextVar("mashi_page", default=(None, False))


def vector_hash(vector):
    return hashlib.sha256(json.dumps(vector, sort_keys=True, allow_nan=False).encode()).hexdigest()


def schema(project):
    version = project.get("schema_version", 1)
    if type(version) is not int or version not in {1, SCHEMA}:
        raise ValueError("This project needs a newer version of Mashi")
    return version


def document(project):
    """Return a raw v2 document in memory; reads never write a migration."""
    version = schema(project)
    if version == 1:
        raw = {key: deepcopy(value) for key, value in project.items() if key not in PAGE_KEYS}
        page = {key: deepcopy(project[key]) for key in PAGE_KEYS if key in project}
        page.update(
            id=project["id"], name=project.get("name", "Page 1"), revision=project["revision"]
        )
        page.setdefault("source_kind", "user-upload")
        page.setdefault("image_asset", "page.png")
        page.setdefault("original_asset", "original.bin")
        page.setdefault("history", [])
        raw.update(
            schema_version=SCHEMA,
            pages=[page],
            sample_choices={},
            selection_required={},
            project_history=[],
        )
        raw.setdefault("typography", {})
        raw.setdefault("proof_text", "")
        raw.setdefault("typography_revision", 1)
        return raw
    raw = {
        key: deepcopy(value) for key, value in project.items() if key not in PAGE_KEYS | VIEW_KEYS
    }
    if project.get("page_id"):
        page = next((p for p in raw["pages"] if p["id"] == project["page_id"]), None)
        if page is None:
            raise ValueError("The selected page is not in this font project")
        for key in PAGE_KEYS:
            if key in project:
                page[key] = deepcopy(project[key])
            else:
                page.pop(key, None)
        page["name"] = project["page_name"]
    return raw


def pages(project):
    if schema(project) == 1:
        return [project]
    # A mutation may be awaiting Store.save; include its current page projection.
    return document(project)["pages"] if project.get("page_id") else project["pages"]


def samples(project):
    result = []
    for page in pages(project):
        for kind, rows in [
            ("captured", page["regions"]),
            ("generated", page.get("completion_suggestions", [])),
        ]:
            for index, row in enumerate(rows):
                if not (
                    row.get("active")
                    and row.get("confirmed")
                    and row.get("label")
                    and row.get("vector")
                ):
                    continue
                if kind == "captured" and row.get("provenance") not in {
                    "observed",
                    "synthetic-fixture",
                }:
                    continue
                if kind == "generated" and (
                    row.get("provenance") != "model-generated"
                    or row.get("review_state") != "accepted"
                ):
                    continue
                result.append((page, row, kind, index))
    return result


def signature(page, row):
    return {
        "page_id": page["id"],
        "region_id": row["id"],
        "revision": row["revision"],
        "vector_sha256": vector_hash(row["vector"]),
    }


def sample_groups(project):
    groups = defaultdict(list)
    for page, row, kind, index in samples(project):
        groups[row["label"]].append(
            {
                **signature(page, row),
                "page_name": page.get("name", "Page"),
                "kind": kind,
                "number": index + 1,
                "provenance": row["provenance"],
            }
        )
    choices = project.get("sample_choices", {})
    required = project.get("selection_required", {})
    return [
        {
            "label": label,
            "samples": entries,
            "choice": choices.get(label),
            "needs_choice": label in required or len(entries) > 1,
            "reason": required.get(label),
        }
        for label, entries in sorted(groups.items())
    ]


def view(raw, page_id=None, *, require_page=False, migration_pending=False):
    raw = document(raw)
    if require_page and len(raw["pages"]) > 1 and page_id is None:
        raise ValueError("Choose a page before editing its crops or photograph")
    selected = next(
        (p for p in raw["pages"] if p["id"] == (page_id or raw["pages"][0]["id"])), None
    )
    if selected is None:
        raise KeyError("Page not found in this project")
    result = deepcopy(raw)
    result.update({key: deepcopy(selected[key]) for key in PAGE_KEYS if key in selected})
    result.update(
        page_id=selected["id"],
        page_name=selected["name"],
        page_revision=selected["revision"],
        migration_pending=migration_pending,
        has_synthetic_pages=any(p.get("source_kind") == "synthetic-fixture" for p in raw["pages"]),
    )
    result["sample_groups"] = sample_groups(raw)
    return result


def invalidate_choices(before, after):
    """Never silently replace an explicitly selected or removed unique sample."""
    current = {row["label"]: [] for _, row, _, _ in samples(after)}
    for page, row, _, _ in samples(after):
        current[row["label"]].append(signature(page, row))
    choices = after.setdefault("sample_choices", {})
    required = after.setdefault("selection_required", {})
    for label, chosen in list(choices.items()):
        if chosen not in current.get(label, []):
            del choices[label]
            required[label] = "The selected sample changed. Choose the form to use again."
    previous = defaultdict(list)
    for page, row, _, _ in samples(before):
        previous[row["label"]].append(signature(page, row))
    for label, entries in previous.items():
        if len(entries) == 1 and label not in choices:
            old = entries[0]
            if not any(
                s["page_id"] == old["page_id"] and s["region_id"] == old["region_id"]
                for s in current.get(label, [])
            ):
                required[label] = (
                    "The sample previously used was removed. Choose a replacement explicitly."
                )


def resolve(project, include_fixture=False, include_generated=False):
    """Preserve each selected form's page identity; do not change its coordinates."""
    grouped = defaultdict(list)
    for page, row, kind, _ in samples(project):
        fixture = (
            page.get("source_kind") == "synthetic-fixture"
            or row["provenance"] == "synthetic-fixture"
        )
        if fixture and not include_fixture or kind == "generated" and not include_generated:
            continue
        grouped[row["label"]].append((page, row, kind))
    selected, conflicts = [], []
    choices, required = project.get("sample_choices", {}), project.get("selection_required", {})
    for label, entries in grouped.items():
        choice = choices.get(label)
        matches = [(p, r, k) for p, r, k in entries if choice == signature(p, r)] if choice else []
        if choice and not matches or not choice and (len(entries) > 1 or label in required):
            conflicts.append(label)
            continue
        page, row, kind = matches[0] if matches else entries[0]
        result = deepcopy(row)
        if schema(project) == SCHEMA:
            result["page_id"] = page["id"]
            result["source_page"] = {
                key: deepcopy(page[key])
                for key in ["id", "name", "source_kind", "image", "source_image", "preparation"]
                if key in page
            }
            # Validation uses this page, not whichever page is open in the UI.
            result["_reference_page"] = page if kind == "generated" else None
        selected.append(result)
    return selected, sorted(conflicts)


def font_is_synthetic(project, selected=None):
    if selected is None:
        return all(p.get("source_kind") == "synthetic-fixture" for p in pages(project))
    return any(
        r["provenance"] == "synthetic-fixture"
        or r.get("source_page", {}).get("source_kind") == "synthetic-fixture"
        for r in selected
    )
