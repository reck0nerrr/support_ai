"""Server-side eligibility for autonomous answers. No account tools or sanctions exist."""

import re
from sqlalchemy import select
from .config import settings
from .models import Attachment, Message, Player, Profile
from .knowledge import active_crm_rules

# Defense in depth alongside the structured model classification. Mixed requests escalate.
SENSITIVE = re.compile(
    r"бан|заблок|разбан|обман|мошенн|взлом|парол|плат[её]ж|оплат|деньг|донат|"
    r"возврат|жалоб|администратор|оператор|сотрудник|оскорб|угроз|читер|списал|пропал|"
    r"\b(ban|banned|appeal|refund|payment|password|hacked|scam|threat|complaint|charged|human|agent)\b|"
    r"шағым|бұғат|ақша|құпиясөз|төлем|қайтар|shikoyat|blokla|to['’ʻ]lov|parol|aldadi|qaytar|шикоят|блокла|тўлов|парол",
    re.IGNORECASE,
)


def eligibility(db, ticket, result):
    if not settings().auto_reply_enabled:
        return False, "Автоответы отключены"
    if settings().ai_provider != "openai":
        return False, "Для автоответа нужна подключённая LLM"
    if ticket.intake != "chat":
        return False, "Обращение создано как жалоба"
    if ticket.assignee_id:
        return False, "Обращение уже назначено сотруднику"
    if result.get("intent") not in {"faq", "smalltalk", "nonsense"}:
        return False, "Требуется разбор ситуации"
    if not result.get("auto_reply_safe") or result.get("requires_account_access", True):
        return False, "Нужны проверка или действия сотрудника"
    if result.get("escalation_reasons") or result.get("missing"):
        return False, "LLM запросила уточнение или участие сотрудника"
    if ticket.category not in {"other", "technical"} or result.get("category") not in {
        "other",
        "technical",
    }:
        return False, "Категория требует ручного рассмотрения"
    if db.scalar(
        select(Attachment.id).where(Attachment.ticket_id == ticket.id).limit(1)
    ):
        return False, "Вложения должен проверить сотрудник"
    texts = db.scalars(
        select(Message.text).where(
            Message.ticket_id == ticket.id, Message.author == "player"
        )
    ).all()
    if SENSITIVE.search("\n".join(texts)):
        return False, "В сообщении есть признаки спорной или персональной ситуации"
    if not result.get("draft", "").strip():
        return False, "Пустой ответ"
    if result["intent"] == "faq":
        keys = set(result.get("rule_ids", []))
        profile = db.get(Profile, ticket.profile_id) if ticket.profile_id else None
        approved = keys & {
            r["id"] for r in active_crm_rules(db, profile.server if profile else "*")
        }
        if not keys or approved != keys:
            return False, "Для ответа об игре нужен утверждённый источник"
    player = db.get(Player, ticket.player_id)
    if not ticket.demo and (
        not player.telegram_id or not settings().telegram_bot_token
    ):
        return False, "Канал доставки не настроен"
    return True, "Простой вопрос или безобидная реплика; персональные действия не нужны"
