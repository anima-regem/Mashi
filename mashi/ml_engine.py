"""Bounded PCA adapter for Mashi-ML commit 7b3f6568 (MIT original engine code).

Inference arithmetic is adapted from src/mashi_ml/model.py; see
licenses/ml/ENGINE-MIT.txt. No template array is loaded or selected, even from
format 2. Checkpoints and source-font geometry are never bundled by this module.
"""

import base64
import hashlib
import io
import json
import math
from pathlib import Path
import sys
import struct
import zipfile

import numpy as np
from PIL import Image

ENGINE_COMMIT = "7b3f65680fb66be27a4c57593848fef75b884e76"
NORMALIZATION = {"width": 96, "height": 64, "em_pixels": 32, "baseline_y": 45, "ink": "black"}
MAX_FILE = 96 * 1024 * 1024
MAX_EXPANDED = 512 * 1024 * 1024


def bounded_zip_directory(payload):
    # Count central records before ZipFile allocates ZipInfo objects. A forged
    # EOCD count must not hide millions of tiny members in a small archive.
    end = payload.rfind(b"PK\x05\x06", max(0, len(payload) - 65557))
    if end < 0 or end + 22 > len(payload):
        raise ValueError("Invalid checkpoint ZIP directory")
    _, disk, directory_disk, count_disk, count, size, offset, comment = struct.unpack_from(
        "<4s4H2LH", payload, end
    )
    if (
        disk
        or directory_disk
        or count_disk != count
        or count not in {5, 7}
        or end + 22 + comment != len(payload)
        or offset + size != end
    ):
        raise ValueError("Checkpoint must contain exactly five or seven bounded members")
    cursor, actual = offset, 0
    while cursor < end:
        if cursor + 46 > end or payload[cursor : cursor + 4] != b"PK\x01\x02":
            raise ValueError("Invalid checkpoint central record")
        name, extra, annotation = struct.unpack_from("<HHH", payload, cursor + 28)
        cursor += 46 + name + extra + annotation
        actual += 1
        if actual > 7 or cursor > end:
            raise ValueError("Checkpoint directory has excessive members")
    if actual != count:
        raise ValueError("Checkpoint directory member count mismatch")


def checkpoint(path, expected_hash):
    path = Path(path)
    if path.suffix != ".npz" or not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError("Choose a configured NPZ checkpoint smaller than 96 MiB")
    with path.open("rb") as stream:
        payload = stream.read(MAX_FILE + 1)
    if len(payload) > MAX_FILE or hashlib.sha256(payload).hexdigest() != expected_hash:
        raise ValueError("Checkpoint size or approved SHA-256 does not match")
    bounded_zip_directory(payload)
    buffer = io.BytesIO(payload)
    with zipfile.ZipFile(buffer) as archive:
        infos = archive.infolist()
        names = [item.filename for item in infos]
        expected = {"format_version.npy", "labels.npy", "mean.npy", "basis.npy", "metadata.npy"}
        if set(names) not in (expected, expected | {"templates.npy", "template_ids.npy"}) or len(
            names
        ) != len(set(names)):
            raise ValueError("Checkpoint has unexpected or duplicate arrays")
        if sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError("Expanded checkpoint exceeds 512 MiB")
        headers = {}
        for item in infos:
            if item.flag_bits & 1 or item.compress_type not in {0, 8}:
                raise ValueError("Unsupported checkpoint compression")
            with archive.open(item) as stream:
                version = np.lib.format.read_magic(stream)
                if version == (1, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_1_0(
                        stream, max_header_size=4096
                    )
                elif version == (2, 0):
                    shape, fortran, dtype = np.lib.format.read_array_header_2_0(
                        stream, max_header_size=4096
                    )
                else:
                    raise ValueError("Unsupported array header")
                if (
                    dtype.hasobject
                    or fortran
                    or len(shape) > 4
                    or any(type(n) is not int or n < 0 or n > 10000 for n in shape)
                ):
                    raise ValueError("Unsafe checkpoint array schema")
                if math.prod(shape) * dtype.itemsize + stream.tell() != item.file_size:
                    raise ValueError("Checkpoint array length contradicts its header")
                headers[item.filename[:-4]] = (shape, dtype)
        n = headers["labels"][0]
        if (
            len(n) != 1
            or not 1 <= n[0] <= 1000
            or headers["labels"][1].kind != "U"
            or headers["labels"][1].itemsize > 128
        ):
            raise ValueError("Invalid trained sequence inventory")
        n = n[0]
        if (
            headers["metadata"][0] != ()
            or headers["metadata"][1].kind != "U"
            or headers["metadata"][1].itemsize > 65536
        ):
            raise ValueError("Invalid checkpoint metadata")
        if headers["format_version"][0] != () or headers["format_version"][1].kind not in "iu":
            raise ValueError("Invalid checkpoint version")
        rank = headers["basis"][0]
        if (
            headers["mean"] != ((n, 64, 96), np.dtype("float32"))
            or len(rank) != 4
            or rank[1:] != (n, 64, 96)
            or not 1 <= rank[0] <= 16
            or headers["basis"][1] != np.dtype("float32")
        ):
            raise ValueError("Invalid learned array dimensions or precision")
        if "templates" in headers:
            shape, dtype = headers["templates"]
            if (
                len(shape) != 4
                or not 1 <= shape[0] <= 32
                or shape[1:] != (n, 64, 96)
                or dtype != np.dtype("float32")
            ):
                raise ValueError("Invalid template header")
            if (
                headers["template_ids"][0] != (shape[0],)
                or headers["template_ids"][1].kind != "U"
                or headers["template_ids"][1].itemsize > 2048
            ):
                raise ValueError("Invalid template ID header")
    buffer.seek(0)
    with np.load(buffer, allow_pickle=False) as data:
        version = data["format_version"].item()
        labels = data["labels"].tolist()
        if len(set(labels)) != len(labels) or any(
            not s
            or len(s) > 32
            or any(not (0x0D00 <= ord(c) <= 0x0D7F or c in "\u200c\u200d") for c in s)
            for s in labels
        ):
            raise ValueError("Invalid exact Malayalam sequence labels")
        metadata = json.loads(data["metadata"].item())
        if not isinstance(metadata, dict):
            raise ValueError("Invalid checkpoint metadata object")
        present = "templates" in data.files
        capabilities = {
            "pca_inference": True,
            "mean_inference": True,
            "template_baselines": present,
            "nearest_template_diagnostic": present,
        }
        if version == 3:
            if (
                present
                or metadata.get("profile") != "pca-inference-v1"
                or metadata.get("capabilities") != capabilities
            ):
                raise ValueError("Checkpoint capability flags contradict inference-only profile")
        elif version != 2 or not present:
            raise ValueError("Unsupported checkpoint format/profile")
        config = metadata.get("inference_config")
        if not isinstance(config, dict) or set(config) - {
            "method",
            "rank",
            "ridge",
            "band",
            "blend",
            "include_template_diagnostics",
        }:
            raise ValueError("Unsupported inference configuration")
        config = {"method": "pca", "rank": 4, "ridge": 0.001, "band": False, "blend": 1.0, **config}
        if config["method"] not in {"pca", "mean"} or config.get(
            "include_template_diagnostics", False
        ):
            raise ValueError("Template inference/diagnostics are disabled in the studio")
        if (
            type(config["rank"]) is not int
            or not 1 <= config["rank"] <= rank[0]
            or type(config["band"]) is not bool
        ):
            raise ValueError("Invalid inference rank or weighting")
        for key, low, high in [("ridge", 1e-8, 10), ("blend", 0, 1)]:
            if (
                type(config[key]) not in {int, float}
                or not math.isfinite(config[key])
                or not low <= config[key] <= high
            ):
                raise ValueError("Invalid bounded inference parameter")
        mean, basis = data["mean"], data["basis"]
        if (
            not np.isfinite(mean).all()
            or not np.isfinite(basis).all()
            or np.max(np.abs(mean)) > 1.01
            or np.max(np.abs(basis)) > 64
        ):
            raise ValueError("Learned arrays have nonfinite or unsupported values")
    return {
        "labels": labels,
        "mean": mean,
        "basis": basis,
        "config": config,
        "format_version": version,
        "profile": metadata.get("profile", "full-v2"),
        "capabilities": capabilities,
        "sha256": expected_hash,
        "engine_commit": ENGINE_COMMIT,
    }


def public_model(model):
    return {
        "adapter_version": "mashi-pca-bridge/v1",
        **{
            key: model[key]
            for key in [
                "labels",
                "format_version",
                "profile",
                "capabilities",
                "sha256",
                "engine_commit",
            ]
        },
        "inference": model["config"],
        "adapter_methods": ["pca", "mean"],
        "template_diagnostics_used": False,
    }


def infer(model, indices, fields):
    """Same PCA/mean arithmetic as the pinned MIT upstream; no template access."""
    fields = np.asarray(fields, np.float32)
    if (
        not indices
        or len(indices) > 20
        or len(set(indices)) != len(indices)
        or fields.shape != (len(indices), 64, 96)
        or not np.isfinite(fields).all()
    ):
        raise ValueError("Invalid aligned observations")
    config = model["config"]
    if config["method"] == "mean":
        return model["mean"].copy()
    rank = config["rank"]
    residual = (fields - model["mean"][indices]).reshape(-1)
    basis = model["basis"][:rank, indices].reshape(rank, -1)
    weights = (
        np.where(np.abs(fields).reshape(-1) < 0.6, 1.0, 0.05).astype(np.float32)
        if config["band"]
        else np.ones(len(residual), np.float32)
    )
    norm = float(weights.sum())
    lhs = (basis * weights) @ basis.T / norm
    rhs = basis @ (weights * residual) / norm
    coeff = np.clip(np.linalg.solve(lhs + config["ridge"] * np.eye(rank), rhs), -4, 4)
    prediction = model["mean"] + config["blend"] * np.tensordot(
        coeff, model["basis"][:rank], axes=1
    )
    return np.clip(prediction, -1, 1).astype(np.float32)


def run(request):
    model = checkpoint(request["checkpoint"], request["sha256"])
    result = {"model": public_model(model)}
    if request["operation"] == "inspect":
        return result
    from scipy.ndimage import distance_transform_edt

    observations, targets = request["observations"], request["targets"]
    if not 1 <= len(observations) <= 20 or not 1 <= len(targets) <= 8:
        raise ValueError("Choose 1–20 references and 1–8 missing sequences")
    labels = [o["label"] for o in observations]
    if (
        len(set(labels)) != len(labels)
        or any(s not in model["labels"] for s in labels + targets)
        or len(set(targets)) != len(targets)
        or set(labels) & set(targets)
    ):
        raise ValueError("References/targets must be unique, supported and disjoint")
    fields = []
    for observation in observations:
        data = base64.b64decode(observation["png"], validate=True)
        if len(data) > 50000 or hashlib.sha256(data).hexdigest() != observation["sha256"]:
            raise ValueError("Observation hash/size mismatch")
        with Image.open(io.BytesIO(data)) as image:
            if image.size != (96, 64):
                raise ValueError("Canonical reference must be 96 × 64")
            mask = np.array(image.convert("L")) < 128
        if not mask.any() or mask.all():
            raise ValueError("An aligned reference has no usable ink")
        fields.append(
            np.clip(
                (distance_transform_edt(mask) - distance_transform_edt(~mask)) / 6.0, -1, 1
            ).astype(np.float32)
        )
    prediction = infer(model, [model["labels"].index(s) for s in labels], np.stack(fields))
    result["suggestions"] = []
    for label in targets:
        mask = prediction[model["labels"].index(label)] >= 0
        output = io.BytesIO()
        Image.fromarray((~mask).astype(np.uint8) * 255).save(output, "PNG")
        result["suggestions"].append(
            {
                "label": label,
                "png": base64.b64encode(output.getvalue()).decode(),
                "sha256": hashlib.sha256(output.getvalue()).hexdigest(),
                "empty": not bool(mask.any()),
            }
        )
    return result


def main():
    try:
        request = json.loads(sys.stdin.read(2_000_001))
        print(json.dumps(run(request), allow_nan=False))
    except Exception as error:
        print(json.dumps({"error": str(error)[:300]}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
