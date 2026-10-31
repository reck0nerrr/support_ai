"""Organizer contract and a strict feature-only boundary for historical exports."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Language = Literal["ru", "kk", "uz", "en", "es", "pt"]
Category = Literal[
    "complaint.insult",
    "complaint.cheat",
    "complaint.dm",
    "complaint.scam",
    "complaint.rmt_ads",
    "complaint.admin",
    "complaint.other",
    "complaint.invalid",
    "report.question",
    "report.help",
    "report.complaint",
    "report.account",
    "report.payment",
    "report.offtopic",
]
Priority = Literal["p0", "p1", "p2", "p3"]
CATEGORIES = tuple(Category.__args__)


class PlayerMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    role: Literal["player", "reported_player"]
    text: str = Field(max_length=24000)
    attachments: int = Field(default=0, ge=0, le=100)


class ContractRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["complaint", "report"]
    messages: list[PlayerMessage] = Field(min_length=1, max_length=40)
    ticket_id: str | int | None = None
    created_at: datetime | None = None
    region: str | None = Field(default=None, max_length=40)
    server_lang: str | None = Field(default=None, max_length=12)
    lang: str | None = Field(default=None, max_length=12)
    reporter_hash: str | None = Field(default=None, max_length=160)
    reported_hash: str | None = Field(default=None, max_length=160)
    reported_nick: str | None = Field(default=None, max_length=100)
    rule_refs_raw: str = Field(default="", max_length=1000)
    images_count: int = Field(default=0, ge=0, le=100)
    server: str | None = Field(default=None, max_length=100)
    # Explicit CRM preference; export.lang and server_lang remain noisy hints.
    reply_language: Language | None = None

    @model_validator(mode="after")
    def valid_messages(self):
        if not any(m.role == "player" for m in self.messages):
            raise ValueError("At least one player message is required")
        if sum(len(m.text) for m in self.messages) > 24000:
            raise ValueError("Combined messages exceed 24000 characters")
        return self

    @property
    def text(self):
        return "\n".join(m.text for m in self.messages if m.role == "player")

    @property
    def evidence_count(self):
        return max(self.images_count, sum(m.attachments for m in self.messages))


class Extracted(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    nickname: str | None
    rule_refs: list[str]
    has_evidence: bool
    server: str | None


class DraftReply(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    lang: Language
    text: str = Field(min_length=1, max_length=3500)
    cited: list[str]


class ContractResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    lang: Language
    category: Category
    priority: Priority
    is_spam_or_duplicate: bool
    extracted: Extracted
    draft_reply: DraftReply
    needs_human: bool
    confidence: float = Field(ge=0, le=1)
    reasons: list[str]


class ModelDecision(ContractResponse):
    intent: Literal["complaint", "faq", "smalltalk", "nonsense"]
    missing: list[str]


class Prediction(ModelDecision):
    ticket_id: str | int | None
    status: Literal["ok", "error"]
    telemetry: dict
    error: str | None = None
    citations: list[dict] = Field(default_factory=list)

    def public(self):
        return ContractResponse.model_validate(
            {k: getattr(self, k) for k in ContractResponse.model_fields}
        )


def parse_export(data):
    """Discard admin replies AND outcome labels before constructing any prompt."""
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    allowed = set(ContractRequest.model_fields) - {"messages"}
    features = {k: v for k, v in data.items() if k in allowed}
    messages = data.get("messages")
    if not isinstance(messages, list):
        raise ValueError("Expected messages")
    features["messages"] = [
        {k: m[k] for k in ("role", "text", "attachments") if k in m}
        for m in messages
        if isinstance(m, dict) and m.get("role") in {"player", "reported_player"}
    ]
    return ContractRequest.model_validate(features)


def legacy_category(category, text=""):
    if category == "complaint.admin":
        import re

        return (
            "appeal"
            if re.search(r"разбан|апелляц|пересмотр|обжал|appeal|unban", text, re.I)
            else "admin"
        )
    if category.startswith("complaint.") or category == "report.complaint":
        return "player"
    return {
        "report.account": "account",
        "report.payment": "payment",
        "report.help": "technical",
    }.get(category, "other")
