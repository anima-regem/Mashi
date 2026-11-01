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
