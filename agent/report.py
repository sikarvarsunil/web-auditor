from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low", "not_observed"]


class Evidence(BaseModel):
    type: Literal["screenshot", "dom", "accessibility", "interaction", "user_input"]
    description: str = Field(min_length=3, max_length=1200)
    location: str | None = Field(default=None, max_length=300)


class Finding(BaseModel):
    heuristic_id: int = Field(ge=1, le=10)
    heuristic_name: str = Field(min_length=3, max_length=120)
    status: Literal["finding", "no_issue_observed", "not_observed"]
    title: str = Field(min_length=3, max_length=200)
    evidence: list[Evidence] = Field(default_factory=list, max_length=8)
    user_impact: str = Field(max_length=1200)
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    recommendation: str = Field(max_length=1600)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class ReviewedPage(BaseModel):
    url: str = Field(max_length=2000)
    title: str | None = Field(default=None, max_length=300)
    image: str = Field(max_length=4_000_000)


class AuditReport(BaseModel):
    audit_mode: Literal["url", "screenshot"]
    source: str = Field(max_length=2000)
    page_title: str | None = None
    viewport: str
    summary: str = Field(min_length=3, max_length=3000)
    findings: list[Finding] = Field(min_length=10, max_length=10)
    methodology_note: str
    model: str
    pages: list[ReviewedPage] = Field(default_factory=list, max_length=3)
