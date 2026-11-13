"""Answer-domain contracts, independent of HTTP, retrieval, and model providers.

A passage identifier establishes provenance. It never proves that a claim follows
from that passage; the separate review contract records that fallible judgment.
"""
from __future__ import annotations

SOURCE_INTRO = "Selected source excerpts. Their wording is literal; relevance and completeness remain subject to review."
COMPARISON_SCOPE = "Comparison is limited to wording in the selected source sections; absence of a listed condition does not establish clinical safety or exclusivity."

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AnswerClaim(StrictContract):
    id: str = Field(pattern=r"^c[1-9][0-9]{0,2}$")
    text: str = Field(min_length=3, max_length=60000)
    passage_ids: list[str] = Field(min_length=1, max_length=8)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("claim text cannot be blank")
        # Public claims are literal source spans, including their whitespace.
        return value

    @field_validator("passage_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if any(not v.strip() for v in value) or len(set(value)) != len(value):
            raise ValueError("passage identifiers must be nonblank and unique")
        return value


AbstentionReason = Literal["insufficient_evidence", "missing_product", "outside_corpus"]


class DraftAnswer(StrictContract):
    status: Literal["answered", "abstained"]
    claims: list[AnswerClaim] = Field(default_factory=list, max_length=20)
    abstention_reason: AbstentionReason | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "answered":
            if not self.claims or self.abstention_reason is not None:
                raise ValueError("answered requires claims and no abstention reason")
        elif self.claims or self.abstention_reason is None:
            raise ValueError("abstained requires a reason and no claims")
        if len({c.id for c in self.claims}) != len(self.claims):
            raise ValueError("claim identifiers must be unique")
        if any(len(c.text) > 2000 for c in self.claims):
            raise ValueError("internal draft claims must remain within 2000 characters")
        return self


class EvidenceQuote(StrictContract):
    passage_id: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=12, max_length=1800)


class ClaimReview(StrictContract):
    claim_id: str = Field(pattern=r"^c[1-9][0-9]{0,2}$")
    supported: bool
    # Historical records can be read, but None never authorizes publication.
    verdict: Literal["entailed", "contradicted", "insufficient"] | None = None
    evidence: list[EvidenceQuote] = Field(default_factory=list, max_length=12)
    flags: list[str] = Field(default_factory=list, max_length=12)


class DraftReview(StrictContract):
    complete: bool
    safe: bool
    claims: list[ClaimReview] = Field(max_length=20)
    flags: list[str] = Field(max_length=20)
    notes: str | None = Field(default=None, max_length=1500)


class Citation(BaseModel):
    file: str
    drug: str | None = None
    source: str | None = None
    section: str | None = None
    passage_id: str | None = None
    excerpt: str | None = None
    product: str | None = None
    product_id: str | None = None
    document_sha256: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    claim_ids: list[str] = Field(default_factory=list)


class GroundingReport(BaseModel):
    verdict: Literal["grounded", "needs_revision", "revised", "ungrounded"]
    supported: bool = False
    flags: list[str] = Field(default_factory=list)
    notes: str | None = None
    claim_checks: list[ClaimReview] = Field(default_factory=list)
    scope: Literal["source_provenance", "semantic_review"] = "semantic_review"


class NumericComparison(StrictContract):
    """A numerical observation, never a clinical eligibility decision."""
    variable: Literal["eGFR"] = "eGFR"
    question_value: str
    source_threshold: str
    relation: Literal["below", "equal", "above"]
    question_unit: str
    source_unit: str
    passage_id: str
    condition: str = "Numerical comparison only. Clinical interpretation requires identical units, body-surface normalization and applicable patient context."
