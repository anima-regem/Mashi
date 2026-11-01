"""A replaceable local predictor boundary; no pretrained completion model is bundled."""

from typing import Protocol
from .projects import pages, resolve

# Coverage inventory, not an assertion that a codepoint equals a visible glyph.
COMMON = list("അആഇഈഉഊഋഎഏഐഒഓഔകഖഗഘങചഛജഝഞടഠഡഢണതഥദധനപഫബഭമയരലവശഷസഹളഴറ")
COMMON += list("ാിീുൂൃെേൈൊോൌ്ൺൻർൽൾൿ")
COMMON += ["ക്ക", "ങ്ങ", "ച്ച", "ഞ്ഞ", "ട്ട", "ണ്ണ", "ത്ത", "ന്ന", "പ്പ", "മ്മ", "ല്ല", "ക്ഷ", "സ്ത്ര"]


class Predictor(Protocol):
    def suggest(self, project: dict, sequences: list[str]) -> list[dict]:
        """Return suggestions with template-generated/model-generated provenance and lineage."""
        ...


class UntrainedPredictor:
    def suggest(self, project, sequences):
        raise ValueError(
            "No trained completion model is installed. Capture the missing forms first."
        )


def coverage(project):
    regions = [r for page in pages(project) for r in page["regions"] if r["active"]]
    selected, conflicts = resolve(project)
    fixture_selected, _ = resolve(project, include_fixture=True)
    observed = {
        r["label"]
        for r in selected
        if r["confirmed"] and r["vector"] and r["provenance"] == "observed"
    }
    generated = [
        r["id"] for r in regions if r["provenance"] not in {"observed", "synthetic-fixture"}
    ]
    generated += [
        r["id"] for page in pages(project) for r in page.get("completion_suggestions", [])
    ]
    return {
        "observed": sorted(observed),
        "missing": [s for s in COMMON if s not in observed],
        "inventory_size": len(COMMON),
        "variant_conflicts": conflicts,
        "generated_excluded": generated,
        "fixtures_excluded": [r["id"] for r in regions if r["provenance"] == "synthetic-fixture"],
        "synthetic_confirmed": [
            r["label"]
            for r in fixture_selected
            if r["provenance"] == "synthetic-fixture" and r["confirmed"] and r["vector"]
        ],
        "predictor": {
            "scope": "bundled fallback only; optional local completion has its own capability endpoint",
            "capabilities_endpoint": "/api/completion/capabilities",
            "available": False,
            "trained": False,
            "reason": "No trained model or reference-font assets are bundled.",
        },
    }
