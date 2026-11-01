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
