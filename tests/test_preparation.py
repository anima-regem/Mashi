import io

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw

from mashi.imaging import decode
from mashi.models import PreparationOptions
from mashi.preparation import geometry, map_points, prepare, source_polygons
from test_workflow import fixture_image, png


def test_geometry_roundtrip_perspective_and_rotation():
    corners = [[20, 10], [280, 30], [300, 180], [10, 190]]
    forward, size = geometry((320, 200), corners, 12)
    points = [[20, 10], [160, 100], [300, 180]]
    np.testing.assert_allclose(
        map_points(map_points(points, forward), np.linalg.inv(forward)), points, atol=1e-7
    )
    assert size[0] > 250 and size[1] > 150
    with pytest.raises(ValueError):
        geometry((320, 200), [[0, 0], [320, 200], [320, 0], [0, 200]], 0)
    with pytest.raises(ValueError):
        geometry((320, 200), [[0, 0], [321, 0], [320, 200], [0, 200]], 0)


def test_cleanup_uneven_light_retains_ring_counter():
    paper = np.tile(np.linspace(245, 100, 320, dtype=np.uint8), (240, 1))
    image = Image.fromarray(paper).convert("RGB")
    ImageDraw.Draw(image).ellipse((100, 60, 220, 180), outline="black", width=12)
    cleaned, _, _ = prepare(
        image, PreparationOptions(illumination=1, mode="adaptive", adaptive_window=51)
    )
    pixels = np.asarray(cleaned)[:, :, 0]
    assert pixels[120, 160] == 255 and pixels[65, 160] == 0
    outside = np.ones((240, 320), bool)
    outside[50:191, 90:231] = False
    assert (pixels[outside] < 128).sum() < (paper[outside] < 180).sum() * 0.1


def test_synthetic_perspective_photo_and_rotation_keep_ink_orientation():
    source = fixture_image()
    corners = np.float32([[50, 30], [350, 50], [370, 260], [30, 270]])
    photo_matrix = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [320, 0], [320, 200], [0, 200]]), corners
    )
    photo = Image.fromarray(
        cv2.warpPerspective(np.array(source), photo_matrix, (400, 300), borderValue=(255, 255, 255))
    )
    prepared, _, metadata = prepare(photo, PreparationOptions(corners=corners.tolist(), rotation=9))
    mapping = np.array(metadata["source_to_working"]) @ photo_matrix
    samples = [[80, 80], [80, 25], [215, 60], [260, 60], [260, 135]]
    expected = [False, True, True, False, True]
    for (x, y), dark in zip(map_points(samples, mapping), expected):
        value = prepared.getpixel((round(x), round(y)))[0]
        assert (value < 128) == dark


def test_exif_to_original_edge_coordinates():
    image = Image.new("RGB", (60, 30), "white")
    exif = Image.Exif()
    exif[274] = 6
    data = io.BytesIO()
    image.save(data, "JPEG", exif=exif)
    _, _, metadata = decode(data.getvalue())
    polygon = source_polygons([0, 0, 30, 60], metadata)["original_polygon"]
    np.testing.assert_allclose(polygon, [[0, 30], [0, 0], [60, 0], [60, 30]])
    metadata.pop("source_to_original")
    np.testing.assert_allclose(
        source_polygons([0, 0, 30, 60], metadata)["original_polygon"], polygon
    )


def test_prepare_api_restore_names_and_crop_provenance(client):
    doc = client.post("/api/projects?source=synthetic-fixture", content=png(fixture_image())).json()
    base = f"/api/projects/{doc['id']}"
    rid = doc["regions"][0]["id"]
    initial_bytes = client.get(base + "/image").content
    r = doc["regions"][0]
    doc = client.put(
        f"{base}/regions/{rid}",
        json={"revision": r["revision"], "box": r["box"], "label": "ക", "confirmed": True},
    ).json()
    previous_regions = doc["regions"]
    params = {
        "rotation": 15,
        "illumination": 0.7,
        "mode": "adaptive",
        "corners": [[0, 0], [320, 0], [320, 200], [0, 200]],
    }
    preview = client.post(base + "/preparation/preview", json=params)
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/png"
    response = client.post(base + "/preparation", json={**params, "revision": doc["revision"]})
    assert response.status_code == 200, response.text
    doc = response.json()
    assert all(not r["confirmed"] and not r["vector"] for r in doc["regions"])
    assert doc["image"]["source_canonical_sha256"] == doc["source_image"]["canonical_sha256"]
    assert client.get(base + "/source-image").content == initial_bytes
    assert all(r["provenance"] == "synthetic-fixture" for r in doc["regions"])
    region = doc["regions"][0]
    expected = source_polygons(region["box"], doc["image"])
    assert region["source_polygon"] == expected["source_polygon"]
    assert client.post(base + "/preparation", json={"revision": 1}).status_code == 409
    doc = client.put(
        f"{base}/regions/{region['id']}",
        json={
            "revision": region["revision"],
            "box": region["box"],
            "label": "അ",
            "confirmed": True,
        },
    ).json()
    region = doc["regions"][0]
    traced = client.post(
        f"{base}/regions/{region['id']}/trace", json={"revision": region["revision"]}
    )
    assert traced.status_code == 200, traced.text
    doc = traced.json()
    assert client.post(base + "/export/ufo?include_fixture=true").status_code == 200
    restored = client.post(base + "/preparation/restore", json={"revision": doc["revision"]})
    assert restored.status_code == 200
    doc = restored.json()
    assert doc["regions"] == previous_regions
    assert client.get(base + "/image").content == initial_bytes
    named = client.put(
        base + "/name", json={"revision": doc["revision"], "name": "  First Malayalam page  "}
    )
    assert named.json()["name"] == "First Malayalam page"
    assert client.get("/api/projects").json()[0]["name"] == "First Malayalam page"


def test_noisy_upload_can_still_be_prepared_or_cropped_manually(client):
    image = Image.new("RGB", (400, 400), "white")
    draw = ImageDraw.Draw(image)
    for x in range(2, 395, 8):
        for y in range(2, 395, 8):
            draw.rectangle((x, y, x + 3, y + 3), fill="black")
    response = client.post("/api/projects?source=synthetic-fixture", content=png(image))
    assert response.status_code == 200
    doc = response.json()
    assert doc["regions"] == [] and "Prepare the photo" in doc["capture_notice"]
    assert (
        client.post(
            f"/api/projects/{doc['id']}/regions",
            json={"box": [0, 0, 20, 20], "project_revision": doc["revision"]},
        ).status_code
        == 200
    )
