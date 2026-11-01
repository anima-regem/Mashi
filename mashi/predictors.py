"""A replaceable local predictor boundary; no pretrained completion model is bundled."""

from typing import Protocol

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
    regions = [r for r in project["regions"] if r["active"]]
    observed = {
        r["label"]
        for r in regions
        if r["confirmed"] and r["vector"] and r["provenance"] == "observed"
    }
    generated = [r["id"] for r in regions if r["provenance"] != "observed"]
    return {
        "observed": sorted(observed),
        "missing": [s for s in COMMON if s not in observed],
        "inventory_size": len(COMMON),
        "generated_excluded": generated,
        "predictor": {
            "available": False,
            "trained": False,
            "reason": "No trained model or reference-font assets are bundled.",
        },
    }
