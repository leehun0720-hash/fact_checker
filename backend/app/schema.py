from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["error", "suspect", "unverifiable", "confirmed"]
Severity = Literal["critical", "major", "minor"]
Category = Literal["계산", "정합", "사실", "출처", "법령", "의견"]
Grade = Literal["A", "B", "C", "D"]


class Lenient(BaseModel):
    """모델이 만든 JSON은 필드가 빠지거나 남을 수 있다. 남는 키는 무시하고 빠진 키는 기본값으로 채운다."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Source(Lenient):
    title: Optional[str] = None
    url: Optional[str] = None
    published: Optional[str] = None


class Evidence(Lenient):
    type: str = "none"
    detail: str = ""
    formula: Optional[str] = None
    sources: list[Source] = Field(default_factory=list)


class Finding(Lenient):
    id: str = ""
    verdict: str = "unverifiable"
    severity: Optional[str] = None
    category: str = "사실"
    location: str = ""
    quote: str = ""
    issue: str = ""
    evidence: Evidence = Field(default_factory=Evidence)
    fix: Optional[str] = None
    user_action: Optional[str] = None
    # 앱이 붙이는 플래그 (예: downgraded_no_evidence)
    flags: list[str] = Field(default_factory=list)


class Recalculation(Lenient):
    location: str = ""
    doc_value: str = ""
    recalc_value: str = ""
    match: Optional[bool] = None
    formula: str = ""
    estimated: bool = False


class Counts(Lenient):
    error: int = 0
    suspect: int = 0
    unverifiable: int = 0
    confirmed: int = 0


class Summary(Lenient):
    grade: str = "C"
    needs_evidence_flag: bool = False
    text: str = ""
    counts: Counts = Field(default_factory=Counts)
    # 앱이 계산해 덧붙이는 값
    severity_counts: dict[str, int] = Field(default_factory=dict)
    critical_suspects: int = 0
    model_grade: Optional[str] = None


class DocumentInfo(Lenient):
    name: str = ""
    pages: Optional[int] = None
    chars: Optional[int] = None
    as_of: Optional[str] = None
    scope: Optional[str] = None
    extraction: str = "ok"


class Stats(Lenient):
    python_runs: int = 0
    web_searches: int = 0
    web_fetches: int = 0


class VerificationResult(Lenient):
    schema_version: str = "1.0"
    document: DocumentInfo = Field(default_factory=DocumentInfo)
    summary: Summary = Field(default_factory=Summary)
    findings: list[Finding] = Field(default_factory=list)
    recalculations: list[Recalculation] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    stats: Stats = Field(default_factory=Stats)
    limits: list[str] = Field(default_factory=list)


# ---------- Job ----------

JobStatus = Literal["queued", "uploading", "running", "postprocessing", "done", "failed"]


class JobOptions(Lenient):
    as_of: Optional[str] = None
    scope: str = "전체"
    notes: Optional[str] = None
    want_corrected: bool = False


class ToolEvent(Lenient):
    at: str
    tool: str  # web_search | web_fetch | bash | editor
    detail: str


class Usage(Lenient):
    input_tokens: int = 0
    output_tokens: int = 0
    web_search_requests: int = 0
    web_fetch_requests: int = 0
    rounds: int = 0


class Job(Lenient):
    id: str
    org_id: str = ""
    user_id: str = ""
    user_email: str = ""
    created_at: str
    updated_at: str
    status: str = "queued"
    filename: str
    size_bytes: int
    extra_files: list[str] = Field(default_factory=list)
    options: JobOptions = Field(default_factory=JobOptions)
    progress: list[ToolEvent] = Field(default_factory=list)
    counters: dict[str, int] = Field(default_factory=dict)
    usage: Usage = Field(default_factory=Usage)
    error: Optional[str] = None
    result: Optional[VerificationResult] = None
    has_report: bool = False
    has_corrected: bool = False
    model: Optional[str] = None

    @staticmethod
    def now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")
