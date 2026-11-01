from test_workflow import fixture_image, png


def test_restore_latest_edited_outline_from_saved_history(client):
    doc = client.post("/api/projects?source=synthetic-fixture", content=png(fixture_image())).json()
    base = f"/api/projects/{doc['id']}"
    first = doc["regions"][0]
    path = f"{base}/regions/{first['id']}"
    doc = client.put(
        path,
        json={"revision": first["revision"], "box": first["box"], "label": "ക", "confirmed": True},
    ).json()
    doc = client.post(path + "/trace", json={"revision": doc["regions"][0]["revision"]}).json()
    first = doc["regions"][0]
    geometry = ["M10 10C20 0 40 0 50 10L50 60L10 60Z"]
    doc = client.put(
        path + "/vector",
        json={
            "revision": first["revision"],
            "paths": geometry,
            "baseline": 70,
            "scale": 2,
            "advance": 321,
        },
    ).json()
    edited = doc["regions"][0]
    doc = client.post(path + "/trace", json={"revision": edited["revision"]}).json()
    history = client.get(path + "/history").json()
    prior = next(e for e in history if e["operation"] == "before-retrace")
    response = client.post(
        path + "/restore",
        json={"revision": doc["regions"][0]["revision"], "history_index": prior["index"]},
    )
    assert response.status_code == 200, response.text
    restored = response.json()["regions"][0]
    assert restored["vector"] == edited["vector"] and restored["label"] == "ക"
    assert restored["revision"] > doc["regions"][0]["revision"]
    assert restored["provenance"] == "synthetic-fixture"
    assert client.post(base + "/export/ufo?include_fixture=true").status_code == 200
    assert any(e["operation"] == "before-restore" for e in client.get(path + "/history").json())
    assert (
        client.post(
            path + "/restore",
            json={"revision": edited["revision"], "history_index": prior["index"]},
        ).status_code
        == 409
    )


def test_history_cannot_restore_another_crop_or_unknown_state(client):
    doc = client.post("/api/projects", content=png(fixture_image())).json()
    base = f"/api/projects/{doc['id']}"
    first, second = doc["regions"][:2]
    doc = client.put(
        f"{base}/regions/{first['id']}",
        json={"revision": first["revision"], "box": first["box"], "label": "ക", "confirmed": True},
    ).json()
    history = client.get(f"{base}/regions/{first['id']}/history").json()
    response = client.post(
        f"{base}/regions/{second['id']}/restore",
        json={"revision": second["revision"], "history_index": history[0]["index"]},
    )
    assert response.status_code == 400
    response = client.post(
        f"{base}/regions/{first['id']}/restore",
        json={"revision": doc["regions"][0]["revision"], "history_index": 99999},
    )
    assert response.status_code == 400
