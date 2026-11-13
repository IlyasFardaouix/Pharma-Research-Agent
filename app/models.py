"""Pydantic request/response schemas for the HTTP API."""

from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from app.answer import AnswerClaim, Citation, ClaimReview, EvidenceQuote, GroundingReport, NumericComparison, COMPARISON_SCOPE

DISCLAIMER = (
    "This is a technical demonstration over a fixed local corpus and is NOT "
    "medical advice. Always consult a qualified healthcare professional and the "
    "official prescribing information before making clinical decisions."
)


class AskRequest(BaseModel):
    """Body of ``POST /ask``."""

    question: str = Field(..., min_length=1, max_length=4000, description="User question.")

    @field_validator("question")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question must not be empty or whitespace")
        return v


class ToolCallTrace(BaseModel):
    """One tool invocation, surfaced for transparency."""

    tool: str
    args: dict = Field(default_factory=dict)
    result_summary: str = ""


class AnswerResponse(BaseModel):
    """Body returned by ``POST /ask``."""

    answer: str
    status: Literal["answered", "abstained"] = "abstained"
    response_mode: Literal["synthesis", "source_excerpts"] = "synthesis"
    numeric_comparisons: list[NumericComparison] = Field(default_factory=list)
    comparison_scope: Literal[COMPARISON_SCOPE] | None = None
    common_terms: list[str] = Field(default_factory=list, max_length=24)
    claims: list[AnswerClaim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER
    plan: list[str] = Field(default_factory=list, description="Sub-questions the agent planned.")
    plan_kind: Literal["research_plan", "workflow_summary"] = "research_plan"
    tool_trace: list[ToolCallTrace] = Field(default_factory=list)
    grounding: GroundingReport | None = None
    warnings: list[str] = Field(
        default_factory=list, description="Critic flags surfaced to the user."
    )

    @model_validator(mode="after")
    def coherent_status(self):
        report = self.grounding
        if self.status == "answered":
            if not self.claims or report is None or not report.supported or report.flags or report.verdict not in {"grounded", "revised"}:
                raise ValueError("answered requires claims and an approved grounding report")
        elif self.claims or self.citations or report is None or report.supported or report.verdict != "ungrounded":
            raise ValueError("abstained requires no claims/citations and an unsupported grounding report")
        if self.response_mode == "source_excerpts" and self.status == "answered":
            if len({c.id for c in self.claims}) != len(self.claims):
                raise ValueError("source excerpt identifiers must be unique")
            if report.scope != "source_provenance":
                raise ValueError("literal excerpts require an explicit source provenance scope")
            cited = {c.passage_id: c for c in self.citations}
            if len(cited) != len(self.citations) or len(self.claims) != len(cited):
                raise ValueError("source excerpts require exactly one citation per unique context")
            for claim in self.claims:
                if len(claim.passage_ids) != 1:
                    raise ValueError("a source excerpt must refer to exactly one context")
                citation = cited.get(claim.passage_ids[0])
                if citation is None or citation.excerpt != claim.text or citation.claim_ids != [claim.id]:
                    raise ValueError("source excerpt text and links must exactly match the server citation")
            if any(n.passage_id not in cited for n in self.numeric_comparisons):
                raise ValueError("numeric observations require a published source context")
        elif self.status == "abstained" and self.numeric_comparisons:
            raise ValueError("abstentions cannot publish numerical conclusions")
        return self


class HealthResponse(BaseModel):
    status: Literal["ok", "starting", "degraded"] = "ok"
    retriever_ready: bool = False
    corpus_files: int = 0
    chunks: int = 0
    llm_configured: bool = False
    answer_timeout: float = 180.0


def public_answer(response: AnswerResponse) -> AnswerResponse:
    """Do not leak unverified clinical prose through model review diagnostics."""
    report = response.grounding
    if report is None:
        return response
    accepted = response.status == "answered"
    safe_report = report.model_copy(update={
        "flags": [] if accepted else (["evidence_not_verified"] if report.flags else []),
        "notes": ("Source excerpts are literal; relevance and completeness were reviewed by a model and may be wrong."
                  if accepted else "No complete verified answer was published."),
        "claim_checks": report.claim_checks if accepted else [],
    })
    notices = ([] if accepted or not report.flags else [
        "The answer was withheld because its evidence could not be verified. Try a narrower question."
    ])
    # The model's plan is an internal research instruction, not medical evidence.
    steps = ["Search the local corpus", "Review the selected evidence",
             "Publish literal source excerpts or abstain"]
    # Search queries are model-authored hypotheses, not documented findings.
    # Keep the actual tool sequence without exposing that free prose as evidence.
    known_tools = {"search_corpus", "get_drug_section", "lookup_glossary", "list_drugs"}
    trace = [ToolCallTrace(tool=item.tool if item.tool in known_tools else "unknown_corpus_tool",
        args={}, result_summary="Local corpus tool invocation recorded.") for item in response.tool_trace]
    return response.model_copy(update={"grounding": safe_report, "warnings": notices,
        "plan": steps, "plan_kind": "workflow_summary", "tool_trace": trace})
