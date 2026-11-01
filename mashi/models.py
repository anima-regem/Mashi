import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RegionInput(BaseModel):
    box: tuple[int, int, int, int]
    label: str = Field(default="", max_length=32)
    confirmed: bool = False

    @field_validator("label")
    @classmethod
    def valid_label(cls, value):
        # Preserve exact codepoints, including ZWJ/ZWNJ. Never normalize here.
        if any(not (0x0D00 <= ord(c) <= 0x0D7F or c in "\u200c\u200d") for c in value):
            raise ValueError("Use Malayalam characters, with optional ZWJ/ZWNJ joiners")
        return value


class RegionEdit(RegionInput):
    revision: int = Field(ge=1)


class RegionCreateInput(RegionInput):
    project_revision: int = Field(ge=1)


class SplitInput(BaseModel):
    revision: int
    axis: Literal["x", "y"]
    position: int


class MergeInput(BaseModel):
    ids: list[str] = Field(min_length=2, max_length=100)
    revisions: list[int] = Field(min_length=2, max_length=100)


class TraceInput(BaseModel):
    revision: int
    threshold: int = Field(default=180, ge=1, le=254)


class VectorInput(BaseModel):
    revision: int
    paths: list[str] = Field(min_length=1, max_length=256)
    baseline: float
    scale: float = Field(gt=0.01, le=100)
    advance: float = Field(ge=0, le=5000)

    @field_validator("baseline", "scale", "advance")
    @classmethod
    def finite(cls, value):
        if not math.isfinite(value):
            raise ValueError("Metrics must be finite")
        return value


class PreparationOptions(BaseModel):
    corners: list[tuple[float, float]] | None = Field(default=None, min_length=4, max_length=4)
    rotation: float = Field(default=0, ge=-180, le=180, allow_inf_nan=False)
    illumination: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    mode: Literal["keep", "global", "adaptive"] = "keep"
    threshold: int = Field(default=180, ge=1, le=254)
    adaptive_window: int = Field(default=51, ge=5, le=151)
    adaptive_bias: int = Field(default=11, ge=-50, le=50)

    @field_validator("adaptive_window")
    @classmethod
    def odd_window(cls, value):
        if value % 2 == 0:
            raise ValueError("Adaptive neighborhood must be odd")
        return value


class PreparationInput(PreparationOptions):
    revision: int = Field(ge=1)


class ProjectNameInput(BaseModel):
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def readable_name(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Choose a nonempty page name without control characters")
        return value


class RevisionInput(BaseModel):
    revision: int = Field(ge=1)


class RegionRestoreInput(RevisionInput):
    history_index: int = Field(ge=0)


class TypographyInput(BaseModel):
    family_name: str = Field(default="Mashi Handwriting", min_length=1, max_length=100)
    ascender: int = Field(default=1000, ge=1, le=16000)
    descender: int = Field(default=-400, ge=-16000, le=0)
    line_gap: int = Field(default=100, ge=0, le=4000)
    space_advance: int = Field(default=300, ge=1, le=5000)
    mark_gap: int = Field(default=40, ge=0, le=1000)
    anchors: dict[str, dict[str, tuple[float, float]]] = Field(default_factory=dict, max_length=512)


class ProofInput(RevisionInput):
    text: str = Field(min_length=1, max_length=1000)
    options: TypographyInput = Field(default_factory=TypographyInput)

    @field_validator("text")
    @classmethod
    def proof_size(cls, value):
        if not value.strip() or value.count("\n") >= 32:
            raise ValueError("Enter visible proof text, at most 1,000 codepoints and 32 lines")
        return value  # Preserve exact text, including joiners and decomposition.


class CompletionJob(RevisionInput):
    model_config = {"extra": "forbid"}
    job_id: str = Field(pattern=r"^[a-f0-9-]{36}$")


class CompletionReferences(RevisionInput):
    model_config = {"extra": "forbid"}
    ids: list[str] = Field(min_length=1, max_length=20)


class CompletionGenerate(CompletionReferences):
    job_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    targets: list[str] = Field(min_length=1, max_length=8)
    reference_hashes: dict[str, str] = Field(max_length=20)
    alignment_confirmed: bool = False

    @field_validator("targets")
    @classmethod
    def exact_targets(cls, values):
        for value in values:
            if not value or len(value) > 32:
                raise ValueError("Choose exact Malayalam sequences up to 32 codepoints")
            RegionInput.valid_label(value)
        return values


class CompletionReview(RevisionInput):
    suggestion_revision: int = Field(ge=1)
    state: Literal["pending", "accepted", "rejected"]


class CompletionVector(VectorInput):
    project_revision: int = Field(ge=1)
