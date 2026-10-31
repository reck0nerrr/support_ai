from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from typing_extensions import NotRequired, TypedDict

Category = Literal[
    "player", "admin", "appeal", "account", "payment", "technical", "other"
]
Status = Literal[
    "new", "analyzing", "needs_info", "review", "in_progress", "resolved", "closed"
]


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class TicketPatch(BaseModel):
    revision: int
    status: Status | None = None
    priority: Literal["normal", "high"] | None = None
    assignee_id: str | None = None
    category: Category | None = None


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=3500)
    request_key: str = Field(min_length=16, max_length=64)
    revision: int
    internal: bool = False

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Message must contain text")
        return value.strip()


class DemoIn(BaseModel):
    nickname: str = Field(min_length=2, max_length=100)
    server: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=10, max_length=10000)
    category: Category = "player"
    language: Literal["ru", "en", "kk", "uz"] = "ru"
    intake: Literal["complaint", "chat"] = "complaint"


class RuleIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    clause: str = Field(default="", max_length=80)
    text: str = Field(min_length=20, max_length=20000)
    url: HttpUrl | Literal[""] = ""
    version: str = Field(min_length=1, max_length=50)
    language: str = Field(default="ru", max_length=12)
    server: str = Field(default="*", max_length=80)
    approved: bool = False


class AIResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    language: Literal["ru", "en", "kk", "uz"]
    category: Category
    summary: str
    claims: list[str]
    verified_facts: list[str]
    missing: list[str]
    escalation_reasons: list[str]
    rule_ids: list[str]
    draft: str
    intent: Literal["complaint", "faq", "smalltalk", "nonsense"] = "complaint"
    auto_reply_safe: bool = False
    requires_account_access: bool = True


class TriageRequest(BaseModel):
    """Public v1 input. Gold labels deliberately aren't accepted here."""

    model_config = ConfigDict(extra="forbid", strict=True)
    id: str | int | None = None
    text: str = Field(min_length=1, max_length=24000)
    language: Literal["auto", "ru", "en", "kk", "uz"] = "auto"
    server: str = Field(default="*", min_length=1, max_length=80)
    intake: Literal["chat", "complaint"] = "chat"
    attachments_count: int = Field(default=0, ge=0, le=100)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Text must not be blank")
        return value.strip()


class Citation(BaseModel):
    id: str
    clause: str
    title: str
    url: str
    version: str


class TriageTelemetry(TypedDict):
    attempt_id: str
    run_id: str
    provider: Literal["offline", "openai"]
    model: str
    latency_ms: int
    llm_latency_ms: int
    cost_usd: float | None
    usage: dict | None
    pricing: str
    prompt_version: NotRequired[str]
    corpus_version: NotRequired[str]
    rates_usd_per_million: NotRequired[dict]
    response_model: NotRequired[str | None]
    reasoning_effort: NotRequired[str]
    provider_error: NotRequired[dict]
    retry_after_seconds: NotRequired[float]
    called_provider: NotRequired[bool]
    routing_mode: NotRequired[str]
    validation_errors: NotRequired[list[dict]]
    retrieved_ids: NotRequired[list[str]]
    retrieved_chars: NotRequired[int]
    request_id: NotRequired[str | None]
    batch_pacing_ms: NotRequired[int]


class TriageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["1.0"] = "1.0"
    id: str | int | None
    status: Literal["ok", "error"]
    language: Literal["ru", "en", "kk", "uz", "es", "pt"]
    category: Category
    intent: Literal["complaint", "faq", "smalltalk", "nonsense"]
    summary: str
    claims: list[str]
    missing_fields: list[str]
    needs_human: bool
    human_reasons: list[str]
    draft: str
    citations: list[Citation]
    telemetry: TriageTelemetry
    error: str | None = None
    contract: dict | None = None


class EvaluationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    dataset_kind: Literal["synthetic", "organizer", "real-reviewed", "unknown"] = (
        "unknown"
    )
    gold: list[dict] = Field(min_length=1, max_length=2000)
    predictions: list[dict] = Field(max_length=2000)
    reviews: list[dict] = Field(default_factory=list, max_length=2000)
