"""Original synthetic software fixtures; no handwriting/style quality claims."""

from copy import deepcopy
import hashlib
import io
import json
import plistlib
import stat
import struct
import zipfile

from fastapi.testclient import TestClient
from fontTools.ttLib import TTFont
import pytest

from mashi.app import create_app
from mashi.projects import PAGE_KEYS
from test_workflow import fixture_image, png
from test_completion_review import ml_client as _ml_client, generation


@pytest.fixture
def ml_client(tmp_path, monkeypatch):
    yield from _ml_client.__wrapped__(tmp_path, monkeypatch)


def ready(client, label="ക"):
    doc = client.post("/api/projects?source=synthetic-fixture", content=png(fixture_image())).json()
    return confirm(client, doc, label)


def confirm(client, doc, label):
    base = f"/api/projects/{doc['id']}"
    suffix = "?page_id=" + doc["page_id"]
    row = doc["regions"][0]
    response = client.put(
        base + f"/regions/{row['id']}" + suffix,
        json={"revision": row["revision"], "box": row["box"], "label": label, "confirmed": True},
    )
    assert response.status_code == 200, response.text
    doc = response.json()
    response = client.post(
        base + f"/regions/{row['id']}/trace" + suffix,
        json={"revision": doc["regions"][0]["revision"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def add_page(client, doc, image=None, source="synthetic-fixture"):
    response = client.post(
        f"/api/projects/{doc['id']}/pages?revision={doc['revision']}&source={source}",
        content=png(image or fixture_image().rotate(90, expand=True)),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_legacy_reads_do_not_migrate_and_first_write_keeps_exact_recovery(client):
    doc = ready(client)
    store = client.app.state.store
    legacy = {key: deepcopy(doc[key]) for key in PAGE_KEYS if key in doc}
    legacy.update(id=doc["id"], revision=doc["revision"], created=doc["created"], name="പഴയ പേജ്")
    legacy["history"].append({"operation": "original-history", "exact": "ന്\u200dന്\u200c"})
    historical = deepcopy(legacy["regions"][0])
    historical["provenance"] = "observed"  # Before the old demo-origin correction.
    legacy["history"].append(
        {"operation": "legacy-origin", "at": legacy["created"], "snapshot": historical}
    )
    exact = json.dumps(legacy, ensure_ascii=False, indent=3) + "\n"
    with store.connect() as db:
        db.execute("UPDATE projects SET doc=? WHERE id=?", (exact, doc["id"]))
    base = f"/api/projects/{doc['id']}"
    read = client.get(base).json()
    assert read["migration_pending"] and read["page_id"] == doc["id"]
    assert read["regions"] == legacy["regions"]
    assert client.get("/api/projects").status_code == 200
    assert client.get(base + "/coverage").status_code == 200
    assert store.raw_text(doc["id"]) == exact
    assert not (store.root / ".migrations").exists()
    changed = client.put(base + "/name", json={"revision": read["revision"], "name": "My font"})
    assert changed.status_code == 200, changed.text
    migrated = json.loads(store.raw_text(doc["id"]))
    assert migrated["schema_version"] == 2 and len(migrated["pages"]) == 1
    assert migrated["pages"][0]["history"] == legacy["history"]
    assert migrated["pages"][0]["regions"] == legacy["regions"]
    recovery = store.root / migrated["migration"]["backup"]
    with zipfile.ZipFile(recovery) as archive:
        assert archive.read("project.json") == exact.encode()
        assert (
            archive.read("assets/original.bin")
            == store.asset(doc["id"], "original.bin").read_bytes()
        )
    client.put(
        base + "/name", json={"revision": changed.json()["revision"], "name": "Renamed font"}
    )
    assert list(recovery.parent.iterdir()) == [recovery]
    restored = client.post("/api/projects/import", content=recovery.read_bytes())
    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] != doc["id"]
    assert restored.json()["regions"] == legacy["regions"]


def test_two_pages_keep_preparation_coordinates_and_export_page_identity(client):
    first = ready(client)
    base = f"/api/projects/{first['id']}"
    original_page = deepcopy(first["pages"][0])
    second = add_page(client, first)
    assert len(second["pages"]) == 2 and second["page_id"] != first["page_id"]
    page_id = second["page_id"]
    source = client.get(base + "/source-image?page_id=" + page_id)
    assert hashlib.sha256(source.content).hexdigest() == second["image"]["canonical_sha256"]
    response = client.post(
        base + "/preparation?page_id=" + page_id,
        json={"revision": second["revision"], "rotation": 7, "illumination": 0.3},
    )
    assert response.status_code == 200, response.text
    prepared = response.json()
    assert prepared["pages"][0] == original_page
    assert prepared["image"]["canonical_sha256"] != second["image"]["canonical_sha256"]
    assert prepared["image"]["working_to_source"]
    traced = confirm(client, prepared, "ഖ")
    assert traced["pages"][0] == original_page
    assert client.get(base + "/image").status_code == 400
    assert (
        client.post(
            base + "/regions", json={"project_revision": traced["revision"], "box": [1, 1, 10, 10]}
        ).status_code
        == 400
    )
    mixed_merge = client.post(
        base + "/merge?page_id=" + page_id,
        json={
            "ids": [first["regions"][0]["id"], traced["regions"][0]["id"]],
            "revisions": [first["regions"][0]["revision"], traced["regions"][0]["revision"]],
        },
    )
    assert mixed_merge.status_code == 404
    response = client.post(
        base + "/export/ttf?include_fixture=true",
        json={"revision": traced["revision"], "text": "കഖ"},
    )
    assert response.status_code == 200, response.text
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        report = json.loads(archive.read("coverage.json"))
        assert {r["page_id"] for r in report["selected_samples"]} == {first["page_id"], page_id}
        snapshot = json.loads(archive.read("project.json"))
        assert len(snapshot["pages"]) == 2
        assert all("history" not in page and "regions" not in page for page in snapshot["pages"])
        directory = "Mashi-Synthetic.ufo/glyphs/"
        names = plistlib.loads(archive.read(directory + "contents.plist"))
        for label, source in [("u0D15", original_page), ("u0D16", traced["pages"][1])]:
            content = archive.read(directory + names[label]).decode()
            assert source["id"] in content and source["image"]["canonical_sha256"] in content
    restored = client.post(
        base + "/preparation/restore?page_id=" + page_id, json={"revision": traced["revision"]}
    ).json()
    assert restored["image"] == second["image"] and restored["pages"][0] == original_page


def choose(client, doc, page, row):
    return client.put(
        f"/api/projects/{doc['id']}/samples/select",
        json={
            "revision": doc["revision"],
            "label": row["label"],
            "page_id": page,
            "region_id": row["id"],
            "sample_revision": row["revision"],
        },
    )


def test_variants_share_one_resolver_and_selected_edits_never_substitute(client):
    first = ready(client)
    doc = confirm(client, add_page(client, first), "ക")
    base = f"/api/projects/{doc['id']}"
    a, b = doc["pages"][0], doc["pages"][1]

    def preflight(current):
        return client.post(
            base + "/proof/preflight?include_fixture=true",
            json={"revision": current["revision"], "text": "ക"},
        )

    assert preflight(doc).json()["coverage"]["variant_conflicts"] == ["ക"]
    assert client.post(base + "/export/ufo?include_fixture=true").status_code == 400
    picked = choose(client, doc, b["id"], b["regions"][0])
    assert picked.status_code == 200, picked.text
    selected = picked.json()
    assert preflight(selected).json()["coverage"]["supported"]
    preview = client.post(
        base + "/proof/preview?include_fixture=true",
        json={"revision": selected["revision"], "text": "ക"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["drawing"]["family_name"] == "Mashi Synthetic Fixture"
    vector = b["regions"][0]["vector"]
    edited = client.put(
        base + f"/regions/{b['regions'][0]['id']}/vector?page_id={b['id']}",
        json={
            "revision": b["regions"][0]["revision"],
            **{k: vector[k] for k in ["paths", "baseline", "scale"]},
            "advance": 913,
        },
    ).json()
    assert "ക" not in edited["sample_choices"] and "ക" in edited["selection_required"]
    assert not preflight(edited).json()["coverage"]["supported"]
    assert choose(client, selected, a["id"], a["regions"][0]).status_code == 409
    selected_a = choose(client, edited, a["id"], a["regions"][0]).json()
    removed = client.delete(
        base
        + f"/regions/{a['regions'][0]['id']}?page_id={a['id']}&revision={a['regions'][0]['revision']}"
    ).json()
    assert "ക" in removed["selection_required"]
    assert not preflight(removed).json()["coverage"]["supported"], (
        "Do not silently switch to the remaining sample"
    )
    current_b = next(p for p in removed["pages"] if p["id"] == b["id"])
    final = choose(client, removed, b["id"], current_b["regions"][0]).json()
    assert final["revision"] > selected_a["revision"]
    exported = client.post(
        base + "/export/ttf?include_fixture=true", json={"revision": final["revision"], "text": "ക"}
    )
    assert exported.status_code == 200, exported.text
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        font = TTFont(io.BytesIO(archive.read("Mashi-Synthetic.ttf")))
        assert font["hmtx"].metrics["u0D15"][0] == 913
        report = json.loads(archive.read("coverage.json"))
        assert report["selected_samples"][0]["page_id"] == b["id"]


def test_editable_backup_roundtrip_preserves_all_pages_history_assets_and_exact_settings(client):
    first = ready(client)
    second = add_page(client, first)
    second = client.post(
        f"/api/projects/{first['id']}/preparation?page_id={second['page_id']}",
        json={"revision": second["revision"], "rotation": 13, "illumination": 0.3},
    ).json()
    second = confirm(client, second, "ഖ")
    base = f"/api/projects/{first['id']}"
    exact = "ന്\u200d ന്\u200c കൊ"
    saved = client.put(
        base + "/typography",
        json={
            "revision": second["revision"],
            "text": exact,
            "options": {"family_name": "My Test Font", "space_advance": 543, "line_gap": 133},
        },
    )
    assert saved.status_code == 200, saved.text
    current = saved.json()
    raw_before = client.app.state.store.raw_text(first["id"])
    backup = client.post(base + "/backup", json={"revision": current["revision"]})
    assert backup.status_code == 200, backup.text
    assert client.app.state.store.raw_text(first["id"]) == raw_before
    with zipfile.ZipFile(io.BytesIO(backup.content)) as archive:
        assert archive.read("project.json") == raw_before.encode()
        assert len([n for n in archive.namelist() if n.startswith("assets/")]) == 5
        assert not any(n.endswith((".npz", ".npy", ".py")) for n in archive.namelist())
    imported = client.post("/api/projects/import", content=backup.content)
    assert imported.status_code == 200, imported.text
    restored = imported.json()
    assert restored["id"] != first["id"] and restored["pages"] == current["pages"]
    assert restored["typography"] == current["typography"] and restored["proof_text"] == exact
    assert client.app.state.store.raw_text(first["id"]) == raw_before
    app = create_app(client.app.state.store.root, testing=True)
    with TestClient(app) as reopened:
        loaded = reopened.get(f"/api/projects/{restored['id']}").json()
        assert loaded["typography"]["space_advance"] == 543 and loaded["proof_text"] == exact


def rewrite_backup(payload, change):
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = {n: archive.read(n) for n in archive.namelist()}
    change(entries)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries.items():
            archive.writestr(name, value)
    return buffer.getvalue()


def test_import_rejects_bad_archives_without_changing_existing_projects(client, monkeypatch):
    doc = ready(client)
    base = f"/api/projects/{doc['id']}"
    backup = client.post(base + "/backup", json={"revision": doc["revision"]}).content
    store = client.app.state.store
    before = store.raw_text(doc["id"])
    changes = [
        lambda e: e.update({"../escape.py": b"print('never execute')"}),
        lambda e: e.update({"/absolute.png": b"bad"}),
        lambda e: e.update({"assets\\escape.png": b"bad"}),
        lambda e: e.update({"PROJECT.JSON": e["project.json"]}),
        lambda e: e.update({"project.json": b"{}"}),
        lambda e: e.update({"assets/original.bin": b"not an image"}),
    ]
    for change in changes:
        result = client.post("/api/projects/import", content=rewrite_backup(backup, change))
        assert result.status_code == 400, result.text
        assert store.raw_text(doc["id"]) == before and len(store.list()) == 1
    with zipfile.ZipFile(io.BytesIO(backup)) as original:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name in original.namelist():
                archive.writestr(name, original.read(name))
            info = zipfile.ZipInfo("assets/symlink.png")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, b"../../outside")
    assert client.post("/api/projects/import", content=buffer.getvalue()).status_code == 400
    monkeypatch.setattr("mashi.backups.MAX_TOTAL", 1)
    assert client.post("/api/projects/import", content=backup).status_code == 400
    assert store.raw_text(doc["id"]) == before and len(store.list()) == 1
    assert not list((store.root / ".staging").iterdir())


def test_future_schema_and_unsafe_geometry_rejected_on_import(client):
    doc = ready(client)
    base = f"/api/projects/{doc['id']}"
    backup = client.post(base + "/backup", json={"revision": doc["revision"]}).content

    def altered(change):
        def modify(entries):
            project = json.loads(entries["project.json"])
            change(project)
            data = json.dumps(project).encode()
            entries["project.json"] = data
            manifest = json.loads(entries["manifest.json"])
            manifest["project_sha256"] = hashlib.sha256(data).hexdigest()
            entries["manifest.json"] = json.dumps(manifest).encode()

        return rewrite_backup(backup, modify)

    for change in [
        lambda p: p.update(schema_version=999),
        lambda p: p.update(typography_revision="1"),
        lambda p: p.update(typography={"space_advance": "543"}),
        lambda p: p["pages"][0].update(history=["invalid"]),
        lambda p: p["pages"][0]["regions"][0]["vector"].update(
            paths=["<svg><script>bad</script></svg>"]
        ),
    ]:
        result = client.post("/api/projects/import", content=altered(change))
        assert result.status_code == 400, result.text
    assert len(client.app.state.store.list()) == 1


def test_generated_backup_keeps_provenance_but_never_loads_or_relicenses_a_model(ml_client):
    doc = ready(ml_client)
    base = f"/api/projects/{doc['id']}"
    row = doc["regions"][0]
    body = generation(ml_client, doc, base, row)
    generated = ml_client.post(base + "/completion/generate", json=body).json()
    backup = ml_client.post(base + "/backup", json={"revision": generated["revision"]})
    assert backup.status_code == 200, backup.text
    ml_client.post("/api/completion/unload")
    imported = ml_client.post("/api/projects/import", content=backup.content)
    assert imported.status_code == 200, imported.text
    restored = imported.json()
    assert restored["completion_suggestions"] == generated["completion_suggestions"]
    assert not ml_client.get("/api/completion/capabilities").json()["loaded"]
    sample = restored["completion_suggestions"][0]
    assert sample["provenance"] == "model-generated" and sample["not_observed_in_photo"]
    assert (
        ml_client.post(
            f"/api/projects/{restored['id']}/export/ufo?include_fixture=true"
        ).status_code
        == 200
    )


def test_migration_failure_and_damaged_recovery_leave_exact_legacy_untouched(client, monkeypatch):
    from mashi import backups

    doc = ready(client)
    store = client.app.state.store
    legacy = {k: deepcopy(doc[k]) for k in PAGE_KEYS if k in doc}
    legacy.update(id=doc["id"], revision=doc["revision"], name="Legacy", created=doc["created"])
    exact = json.dumps(legacy, indent=2)
    with store.connect() as db:
        db.execute("UPDATE projects SET doc=? WHERE id=?", (exact, doc["id"]))
    original = backups._build

    def fail(*args):
        raise OSError("Synthetic disk failure")

    monkeypatch.setattr(backups, "_build", fail)
    response = client.put(
        f"/api/projects/{doc['id']}/name", json={"revision": doc["revision"], "name": "Migrate"}
    )
    assert response.status_code == 400 and store.raw_text(doc["id"]) == exact
    monkeypatch.setattr(backups, "_build", original)
    recovery = backups.migration_backup(store, legacy, exact.encode())
    path = store.root / recovery["backup"]
    path.write_bytes(
        rewrite_backup(
            path.read_bytes(), lambda entries: entries.update({"assets/page.png": b"damaged"})
        )
    )
    response = client.put(
        f"/api/projects/{doc['id']}/name", json={"revision": doc["revision"], "name": "Migrate"}
    )
    assert response.status_code == 400 and store.raw_text(doc["id"]) == exact


def test_zip_directory_encryption_duplicates_and_limits_are_checked_before_publication(
    client, monkeypatch
):
    from mashi import backups

    doc = ready(client)
    base = f"/api/projects/{doc['id']}"
    payload = client.post(base + "/backup", json={"revision": doc["revision"]}).content
    encrypted = bytearray(payload)
    central = encrypted.index(b"PK\x01\x02")
    struct.pack_into(
        "<H", encrypted, central + 8, struct.unpack_from("<H", encrypted, central + 8)[0] | 1
    )
    wrong_count = bytearray(payload)
    end = wrong_count.rindex(b"PK\x05\x06")
    struct.pack_into("<HH", wrong_count, end + 8, 2, 2)
    duplicate = io.BytesIO(payload)
    with pytest.warns(UserWarning, match="Duplicate"):
        with zipfile.ZipFile(duplicate, "a") as archive:
            archive.writestr("project.json", b"{}")
    for bad in [encrypted, wrong_count, duplicate.getvalue()]:
        assert client.post("/api/projects/import", content=bytes(bad)).status_code == 400
    for key in ["MAX_ARCHIVE", "MAX_ASSET", "MAX_ENTRIES", "MAX_PIXELS"]:
        with monkeypatch.context() as patch:
            patch.setattr(backups, key, 1)
            assert client.post("/api/projects/import", content=payload).status_code in {400, 413}
    assert len(client.app.state.store.list()) == 1
    assert not list((client.app.state.store.root / ".staging").iterdir())


def test_import_staging_failure_preserves_every_existing_asset_and_future_reads_do_not_write(
    client, monkeypatch
):
    from mashi import backups

    doc = ready(client)
    store = client.app.state.store
    base = f"/api/projects/{doc['id']}"
    payload = client.post(base + "/backup", json={"revision": doc["revision"]}).content
    before = store.raw_text(doc["id"])
    assets = {p.name: p.read_bytes() for p in (store.root / doc["id"]).iterdir()}

    def fail(*args):
        raise OSError("Synthetic staging publication failure")

    monkeypatch.setattr(backups.os, "replace", fail)
    assert client.post("/api/projects/import", content=payload).status_code == 400
    assert store.raw_text(doc["id"]) == before
    assert assets == {p.name: p.read_bytes() for p in (store.root / doc["id"]).iterdir()}
    assert len(store.list()) == 1
    future = json.loads(before)
    future["schema_version"] = 999
    exact = json.dumps(future)
    with store.connect() as db:
        db.execute("UPDATE projects SET doc=? WHERE id=?", (exact, doc["id"]))
    assert client.get(base).status_code == 400
    assert store.raw_text(doc["id"]) == exact


def test_settings_survive_restart_and_drive_actual_export_and_mixed_fixture_scope(client):
    # These are synthetic software drawings. The user-upload path exercises metadata handling.
    first = client.post("/api/projects", content=png(fixture_image())).json()
    first = confirm(client, first, "ക")
    doc = confirm(client, add_page(client, first), "ഖ")
    base = f"/api/projects/{doc['id']}"
    doc = client.put(
        base + "/typography",
        json={
            "revision": doc["revision"],
            "text": "ക",
            "options": {"family_name": "Saved Family", "space_advance": 543, "line_gap": 133},
        },
    ).json()
    app = create_app(client.app.state.store.root, testing=True)
    with TestClient(app) as reopened:
        reopened.headers["x-mashi-token"] = reopened.get("/api/session").json()["token"]
        response = reopened.post(base + "/export/ttf")
        assert response.status_code == 200, response.text
        assert 'filename="Mashi-ttf.zip"' in response.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert "Mashi-Experimental.ttf" in archive.namelist()
            font = TTFont(io.BytesIO(archive.read("Mashi-Experimental.ttf")))
            assert font["hmtx"].metrics["space"][0] == 543
            assert font["hhea"].lineGap == 133
            assert font["name"].getDebugName(1) == "Saved Family"
            snapshot = json.loads(archive.read("project.json"))
            assert [r["label"] for r in snapshot["regions"]] == ["ക"]
            assert len(snapshot["pages"]) == 1
        response = reopened.post(base + "/export/ttf?include_fixture=true")
        assert (
            response.status_code == 200 and "SYNTHETIC" in response.headers["content-disposition"]
        )
        assert (
            reopened.post(base + "/pages?revision=1", content=png(fixture_image())).status_code
            == 409
        )
        assert reopened.post(base + "/backup", json={"revision": 1}).status_code == 409


def test_multi_page_generated_output_uses_its_own_references_and_never_leaks_into_normal_export(
    ml_client, monkeypatch
):
    import mashi.ml_service as service

    original = service.source_terms

    # Unit-only registry stand-in; these tiny synthetic arrays are not trained weights.
    def fixture_terms(digest):
        return original(
            "0165690674d47818bd66055cf66f7b8861bdbb557f964bea56154b33180ea045"
            if digest == ml_client.app.state.completion.digest
            else digest
        )

    monkeypatch.setattr(service, "source_terms", fixture_terms)
    monkeypatch.setattr("mashi.exporting.source_terms", fixture_terms)
    first = ready(ml_client)
    base = f"/api/projects/{first['id']}"
    generated = ml_client.post(
        base + "/completion/generate", json=generation(ml_client, first, base, first["regions"][0])
    ).json()
    candidate = generated["completion_suggestions"][0]
    accepted = ml_client.post(
        base + f"/completion/suggestions/{candidate['id']}/review",
        json={
            "revision": generated["revision"],
            "suggestion_revision": candidate["revision"],
            "state": "accepted",
        },
    ).json()
    second = confirm(ml_client, add_page(ml_client, accepted), "ഗ")
    # The open page is now different; export must validate the first page's references.
    ordinary = ml_client.post(
        base + f"/export/ufo?include_fixture=true&page_id={second['page_id']}"
    )
    assert ordinary.status_code == 200, ordinary.text
    with zipfile.ZipFile(io.BytesIO(ordinary.content)) as archive:
        snapshot = json.loads(archive.read("project.json"))
        assert snapshot["completion_suggestions"] == []
        assert not any(name.startswith("FONT-LICENSES/") for name in archive.namelist())
        for name in archive.namelist():
            assert candidate["vector"]["paths"][0].encode() not in archive.read(name), name
    explicit = ml_client.post(
        base
        + f"/export/ttf?include_fixture=true&include_generated=true&page_id={second['page_id']}",
        json={"revision": second["revision"], "text": "ഖ"},
    )
    assert explicit.status_code == 200, explicit.text
    with zipfile.ZipFile(io.BytesIO(explicit.content)) as archive:
        snapshot = json.loads(archive.read("project.json"))
        assert snapshot["completion_suggestions"][0]["page_id"] == first["page_id"]
        assert archive.read("FONT-LICENSES/OFL.txt")
        assert candidate["id"] in archive.read("GENERATED-PROVENANCE.json").decode()


def test_exact_joiner_sequences_have_independent_choices(client):
    first = ready(client, "ന്\u200d")
    second = confirm(client, add_page(client, first), "ന്\u200c")
    groups = second["sample_groups"]
    assert {g["label"] for g in groups} == {"ന്\u200d", "ന്\u200c"}
    assert not any(g["needs_choice"] for g in groups)
    chosen = choose(client, second, first["page_id"], first["regions"][0]).json()
    assert set(chosen["sample_choices"]) == {"ന്\u200d"}


def test_import_streams_inflate_calls_and_rejects_complex_or_duplicate_json(client, monkeypatch):
    doc = ready(client)
    payload = client.post(
        f"/api/projects/{doc['id']}/backup", json={"revision": doc["revision"]}
    ).content
    calls = []
    original = zipfile.ZipExtFile.read

    def bounded(stream, size=-1):
        assert 0 < size <= 65536, "Unbounded archive decompression"
        calls.append(size)
        return original(stream, size)

    monkeypatch.setattr(zipfile.ZipExtFile, "read", bounded)
    restored = client.post("/api/projects/import", content=payload)
    assert restored.status_code == 200 and calls
    monkeypatch.setattr(zipfile.ZipExtFile, "read", original)

    def invalid_json(data):
        def change(entries):
            entries["project.json"] = data
            manifest = json.loads(entries["manifest.json"])
            manifest["project_sha256"] = hashlib.sha256(data).hexdigest()
            entries["manifest.json"] = json.dumps(manifest).encode()

        return rewrite_backup(payload, change)

    for data in [
        b'{"schema_version":2,"schema_version":2}',
        b'{"x":NaN}',
        b'{"x":1e999}',
        b"[" * 45 + b"0" + b"]" * 45,
    ]:
        assert client.post("/api/projects/import", content=invalid_json(data)).status_code == 400
    assert len(client.app.state.store.list()) == 2
