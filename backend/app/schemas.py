from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

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
    language: Literal["ru", "en"] = "ru"
    intake: Literal["complaint", "chat"] = "complaint"


class RuleIn(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    clause: str = Field(default="", max_length=80)
    text: str = Field(min_length=20, max_length=20000)
    url: HttpUrl
    version: str = Field(min_length=1, max_length=50)
    language: str = Field(default="ru", max_length=12)
    server: str = Field(default="*", max_length=80)
    approved: bool = False


class AIResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    language: str
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
