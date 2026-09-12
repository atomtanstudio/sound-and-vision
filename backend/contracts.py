from __future__ import annotations
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Sampling(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    temperature: float = Field(default=1, ge=0, le=5)
    top_p: float = Field(default=0.95, gt=0, le=1)
    top_k: int = Field(default=100, ge=1, le=184704, strict=True)
    repetition_penalty: float = Field(default=1.2, gt=0)
    penalty_window: int = Field(default=50, ge=1, le=100, strict=True)
    min_tokens: int = Field(default=200, ge=0, strict=True)
    max_tokens: int = Field(default=9000, ge=1, le=24576, strict=True)

    @model_validator(mode="after")
    def token_range(self):
        if self.min_tokens > self.max_tokens:
            raise ValueError("Minimum tokens must not exceed maximum tokens.")
        return self


class SongForm(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    description: str = Field(default="", max_length=20000)
    title: str = Field(default="", max_length=200)
    lyrics: str = Field(default="", max_length=100000)
    style: str = Field(default="", max_length=20000)
    count: Literal[1, 2] = 2
    project: str = Field(default="Loose tracks", min_length=1, max_length=80)
    cot: Literal["full", "melody", "off"] = "full"
    abc: str = Field(default="", max_length=100000)
    seed: str = ""
    cfg_scale: str = ""
    planFirst: bool = False
    ode_steps: int = Field(default=32, ge=1, le=1000, strict=True)
    semantic: Sampling = Field(default_factory=Sampling)
    score: Sampling = Field(
        default_factory=lambda: Sampling(
            temperature=0.7,
            top_p=0.9,
            top_k=30,
            repetition_penalty=1.005,
            penalty_window=100,
            min_tokens=32,
            max_tokens=4096,
        )
    )
    genre: str = Field(default="", max_length=80)
    referenceId: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    sourceTakeId: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    writingTask: str = Field(default="Draft lyrics", max_length=100)
    writingPrompt: str = Field(default="", max_length=20000)

    @field_validator("seed")
    @classmethod
    def valid_seed(cls, value):
        if value and (
            not value.isascii()
            or not value.isdigit()
            or len(value) > 19
            or not 0 <= int(value) < 2**63
        ):
            raise ValueError(
                "Seed must be an integer from 0 through 9223372036854775807."
            )
        return value

    @field_validator("cfg_scale")
    @classmethod
    def valid_guidance(cls, value):
        if value and (not math.isfinite(float(value)) or not 0 <= float(value) <= 20):
            raise ValueError("Guidance must be between 0 and 20.")
        return value

    @model_validator(mode="after")
    def usable_song(self):
        if not (self.style.strip() or self.description.strip()):
            raise ValueError("Add a song description or style.")
        if not self.lyrics.strip():
            raise ValueError(
                "Add lyrics before generating. Review and apply a writing proposal if needed."
            )
        if not self.project.strip():
            raise ValueError("Project name cannot be blank.")
        return self


class GenerationSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{7,99}$")
    form: SongForm


class TrackPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=200)
    project: str | None = Field(default=None, min_length=1, max_length=80)
    favorite: bool | None = None

    @field_validator("title", "project")
    @classmethod
    def not_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("Cannot be blank.")
        return value


class ContinuePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    abc: str | None = Field(default=None, max_length=100000)
