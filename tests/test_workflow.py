import io
import json
import zipfile

import pytest
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.svgLib.path import parse_path
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw
from ufoLib2 import Font

from mashi.exporting import export_bundle, glyph_name, make_ufo
from mashi.imaging import decode, sha
from mashi.tracing import trace, validate_paths


def fixture_image():
    image = Image.new("RGB", (320, 200), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((20, 20, 140, 140), outline="black", width=12)
    draw.rectangle((210, 30, 225, 145), fill="black")
    draw.rectangle((210, 130, 290, 145), fill="black")
    return image


def png(image):
    data = io.BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def upload(client):
    response = client.post("/api/projects", content=png(fixture_image()))
    assert response.status_code == 200, response.text
    return response.json()


def test_exif_orientation_and_hashes():
    image = Image.new("RGB", (60, 30), "white")
    ImageDraw.Draw(image).rectangle((0, 0, 29, 29), fill="black")
    exif = Image.Exif()
    exif[274] = 6
    data = io.BytesIO()
    image.save(data, format="JPEG", exif=exif)
    canonical, encoded, metadata = decode(data.getvalue())
    assert canonical.size == (30, 60)
    assert canonical.getpixel((15, 10))[0] < 10
    assert canonical.getpixel((15, 50))[0] > 245
    assert metadata["original_sha256"] == sha(data.getvalue())
    assert metadata["canonical_sha256"] == sha(encoded)
    assert metadata["transforms"][0]["orientation"] == 6


def test_regions_split_merge_and_exact_unicode(client):
    project = upload(client)
    base = f"/api/projects/{project['id']}"
    region = project["regions"][0]
    exact = "ക്\u200dക\u200c"
    edit = {
        "box": [10, 10, 150, 155],
        "label": exact,
        "confirmed": True,
        "revision": region["revision"],
    }
    response = client.put(f"{base}/regions/{region['id']}", json=edit)
    assert response.status_code == 200
    region = response.json()["regions"][0]
    assert region["label"] == exact
    assert client.put(f"{base}/regions/{region['id']}", json=edit).status_code == 409
    response = client.post(
        f"{base}/regions/{region['id']}/split",
        json={"revision": region["revision"], "axis": "x", "position": 80},
    )
    assert response.status_code == 200
    doc = response.json()
    assert doc["regions"][0]["active"] is False
    children = doc["regions"][-2:]
    assert children[0]["box"] == [10, 10, 80, 155]
    assert children[1]["box"] == [80, 10, 150, 155]
    assert all(r["parents"] == [region["id"]] and not r["confirmed"] for r in children)
    response = client.post(
        f"{base}/merge",
        json={"ids": [r["id"] for r in children], "revisions": [r["revision"] for r in children]},
    )
    merged = response.json()["regions"][-1]
    assert merged["box"] == [10, 10, 150, 155]
    assert merged["parents"] == [r["id"] for r in children]
    assert not merged["confirmed"] and merged["label"] == ""
    assert doc["history"][1]["snapshot"]["label"] == ""


def test_ocr_suggestions_remain_words_and_unconfirmed(client, monkeypatch):
    doc = upload(client)
    suggestion = {
        "box": [10, 10, 150, 160],
        "raw_text": "മഷി\u200d",
        "confidence": 20,
        "granularity": "word",
    }
    monkeypatch.setattr("mashi.ocr.recognize", lambda path: [suggestion])
    response = client.post(f"/api/projects/{doc['id']}/ocr")
    item = response.json()["regions"][-1]
    assert not item["confirmed"] and item["label"] == ""
    assert item["suggestion"] == suggestion
    assert item["source"] == "ocr-word"


def test_trace_retains_counter_and_orientation():
    vector = trace(fixture_image(), 180)
    pen = PointInsidePen(None, (80, 80))
    for d in vector["paths"]:
        parse_path(d, pen)
    assert not pen.getResult(), "Ring counter must remain empty"
    for point, expected in [
        ((80, 24), True),
        ((215, 60), True),
        ((260, 60), False),
        ((260, 135), True),
        ((310, 180), False),
    ]:
        pen = PointInsidePen(None, point)
        for d in vector["paths"]:
            parse_path(d, pen)
        assert pen.getResult() is expected


def test_full_image_to_export(client, tmp_path):
    doc = upload(client)
    base = f"/api/projects/{doc['id']}"
    region = doc["regions"][0]
    response = client.put(
        f"{base}/regions/{region['id']}",
        json={
            "box": region["box"],
            "label": "ക",
            "confirmed": True,
            "revision": region["revision"],
        },
    )
    region = response.json()["regions"][0]
    response = client.post(
        f"{base}/regions/{region['id']}/trace",
        json={"revision": region["revision"], "threshold": 180},
    )
    assert response.status_code == 200, response.text
    doc = response.json()
    region = doc["regions"][0]
    vector = region["vector"]
    assert vector["paths"]
    response = client.put(
        f"{base}/regions/{region['id']}/vector",
        json={
            "revision": region["revision"],
            "paths": vector["paths"],
            "baseline": vector["baseline"],
            "scale": vector["scale"],
            "advance": 777,
        },
    )
    assert response.status_code == 200
    assert response.json()["regions"][0]["vector"]["edited"]
    assert client.get(f"{base}/regions/{region['id']}/svg").status_code == 200
    response = client.post(f"{base}/export/ttf")
    assert response.status_code == 200, response.text
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    report = json.loads(archive.read("coverage.json"))
    assert report["experimental"] and report["encoded_codepoints"] == ["U+0D15"]
    assert not any(n.endswith(".png") or n.endswith(".bin") for n in archive.namelist())
    archive.extractall(tmp_path / "export")
    font = Font.open(tmp_path / "export/Mashi-Handwriting.ufo")
    glyph = font[glyph_name("ക")]
    assert glyph.unicodes == [0x0D15] and len(glyph.contours) >= 2 and glyph.width == 777
    bounds = BoundsPen(font)
    glyph.draw(bounds)
    assert bounds.bounds[1] < 0 < bounds.bounds[3], "Explicit baseline and Y flip"
    ttf = TTFont(io.BytesIO(archive.read("Mashi-Experimental.ttf")))
    assert ttf.getBestCmap()[0x0D15] == glyph_name("ക")
    assert ttf["glyf"][glyph_name("ക")].numberOfContours >= 2
    reopened = client.get(base).json()
    assert reopened["regions"][0]["label"] == "ക"


def synthetic_project(labels):
    vector = trace(fixture_image().crop((10, 10, 150, 150)), 180)
    return {
        "id": "fixture",
        "image": {"canonical_sha256": "synthetic"},
        "regions": [
            {
                "id": str(i),
                "active": True,
                "confirmed": True,
                "label": label,
                "provenance": "observed",
                "revision": 1,
                "box": [10, 10, 150, 150],
                "vector": vector,
            }
            for i, label in enumerate(labels)
        ],
    }


def test_generated_and_unconfirmed_excluded():
    doc = synthetic_project(["ക", "ഖ", "ഗ"])
    doc["regions"][1]["provenance"] = "model-generated"
    doc["regions"][2]["confirmed"] = False
    font, report = make_ufo(doc)
    assert glyph_name("ക") in font and glyph_name("ഖ") not in font and glyph_name("ഗ") not in font
    assert report["generated_excluded"] == ["1"]
    assert not report["predictor"]["trained"]


def test_no_unverified_shaping_dependencies():
    font, report = make_ufo(synthetic_project(["ക", "ക്ക"]))
    assert font.features.text == "" and report["unencoded_sequences"] == ["ക്ക"]


def test_selected_shaping_and_honest_missing_marks():
    import uharfbuzz as hb

    doc = synthetic_project(["ക", "്", "ക്ക", "ൻ", "ി"])
    bundle = zipfile.ZipFile(io.BytesIO(export_bundle(doc, "ttf")))
    data = bundle.read("Mashi-Experimental.ttf")
    tt = TTFont(io.BytesIO(data))
    font = hb.Font(hb.Face(data))

    def shape(text):
        buffer = hb.Buffer()
        buffer.add_str(text)
        buffer.guess_segment_properties()
        hb.shape(font, buffer)
        return [tt.getGlyphName(info.codepoint) for info in buffer.glyph_infos]

    assert shape("ക്ക") == [glyph_name("ക്ക")]
    assert shape("ൻ") == [glyph_name("ൻ")]
    report = json.loads(bundle.read("coverage.json"))
    assert len(shape("കി")) >= 2
    assert any("No mark anchors" in warning for warning in report["warnings"])
    assert "GPOS" not in tt


def test_input_security_and_bounds(client):
    assert client.get("/", headers={"host": "attacker.example"}).status_code == 400
    assert (
        client.get("/api/session", headers={"origin": "https://attacker.example"}).status_code
        == 403
    )
    assert (
        client.post("/api/projects", content=b"x", headers={"x-mashi-token": ""}).status_code == 403
    )
    assert client.post("/api/projects", content=b"<svg></svg>").status_code == 400
    assert (
        client.post(
            "/api/projects", content=b"x", headers={"content-length": "13000000"}
        ).status_code
        == 413
    )
    doc = upload(client)
    assert (
        client.post(
            f"/api/projects/{doc['id']}/regions", json={"box": [-1, 0, 100, 100]}
        ).status_code
        == 400
    )
    with pytest.raises(ValueError):
        validate_paths(["<script>alert(1)</script>"])
    with pytest.raises(ValueError):
        validate_paths(["M0 0L10 10"])
    with pytest.raises(ValueError):
        validate_paths(["M0 0L1e300 10Z"])
