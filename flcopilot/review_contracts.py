"""Audio-review requests carry asset IDs, never filesystem paths or DAW commands."""
from typing import Literal
from pydantic import Field, model_validator, field_validator
from .contracts import Strict


class ReviewRequest(Strict):
    baseline: str = Field(pattern=r"^[a-f0-9]{32}$")
    candidate: str = Field(pattern=r"^[a-f0-9]{32}$")
    confirm_same_range: Literal[True]
    title: str = Field(default="Before / after review", min_length=1, max_length=100)
    section_seconds: int = Field(default=15, ge=10, le=60)
    linked_plan_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")

    @field_validator("confirm_same_range", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Matching export range must be confirmed with boolean true")
        return value

    @model_validator(mode="after")
    def distinct_inputs(self):
        if self.baseline == self.candidate:
            raise ValueError("Choose separate baseline and candidate assets")
        if not self.title.strip() or any(ord(c) < 32 for c in self.title):
            raise ValueError("Review title must be nonblank printable text")
        return self


class ReviewDecision(Strict):
    review_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    expected_revision: int = Field(ge=1)
    decision: Literal["undecided", "prefer_baseline", "prefer_candidate", "needs_revision"]
    note: str = Field(default="", max_length=2000)


class ReviewID(Strict):
    review_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class BlindTrialID(Strict):
    trial_id: str = Field(pattern=r"^[a-f0-9]{32}$")


class BlindTrialSubmit(BlindTrialID):
    guess: Literal["a", "b", "unsure"]
