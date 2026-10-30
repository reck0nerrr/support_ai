from unittest.mock import patch
import httpx
import pytest
from sqlalchemy import select
from app.config import settings
from app.db import session_factory
from app.models import Message, Player, Rule, Ticket
from app.services import create_ticket, player_message
from app.telegram import handle_update
from app.worker import run_once


def simple_result(intent="smalltalk", **overrides):
    return {
        "language": "ru",
        "category": "other",
        "summary": "Простая реплика",
        "claims": [],
        "verified_facts": [],
        "missing": [],
        "escalation_reasons": [],
        "rule_ids": [],
        "draft": "Привет! Чем помочь с игрой?",
        "intent": intent,
        "auto_reply_safe": True,
        "requires_account_access": False,
        **overrides,
    }


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")
    monkeypatch.setenv("OPENAI_MODEL", "fake-model")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-bot")
    settings.cache_clear()


def create_chat(text="Привет!", intake="chat", demo=True):
    with session_factory()() as db, db.begin():
        player = Player(name="Игрок", telegram_id=None if demo else 12345)
        db.add(player)
        db.flush()
        return create_ticket(db, player, None, text, demo=demo, intake=intake).id


def test_harmless_auto_reply_is_saved_without_staff(connected):
    key = create_chat()
    with patch("app.worker.analyze", return_value=(simple_result(), [])):
        assert run_once()
    with session_factory()() as db:
        ticket = db.get(Ticket, key)
        assert ticket.status == "resolved"
        reply = db.scalar(select(Message).where(Message.author == "assistant"))
        assert reply.text == "Привет! Чем помочь с игрой?" and reply.delivery == "demo"
        assert reply.staff_id is None


@pytest.mark.parametrize(
    "text,intake,result",
    [
        ("Здравствуйте, меня обманули и заблокировали", "chat", simple_result()),
        ("Привет!", "complaint", simple_result()),
        ("Как получить водительское удостоверение?", "chat", simple_result("faq")),
        ("Привет!", "chat", simple_result(requires_account_access=True)),
        ("Привет!", "chat", simple_result(escalation_reasons=["Нужна проверка"])),
    ],
)
def test_auto_reply_rejected_when_human_or_sources_needed(
    connected, text, intake, result
):
    key = create_chat(text, intake)
    with patch("app.worker.analyze", return_value=(result, [])):
        run_once()
    with session_factory()() as db:
        assert db.get(Ticket, key).status == "review"
        assert not db.scalar(select(Message).where(Message.author == "assistant"))


def test_faq_uses_approved_source(connected):
    key = create_chat("Как начать работать в игре?")
    with session_factory()() as db, db.begin():
        rule = Rule(
            title="Работы",
            text="Описание начала работы в игре.",
            url="https://support.grnd.gg/ru/",
            version="test",
            approved=True,
        )
        db.add(rule)
        db.flush()
        source = rule.id
    with patch(
        "app.worker.analyze", return_value=(simple_result("faq", rule_ids=[source]), [])
    ):
        run_once()
    with session_factory()() as db:
        assert db.get(Ticket, key).status == "resolved"


def test_free_text_dialog_and_telegram_auto_delivery(connected):
    with session_factory()() as db, db.begin():
        handle_update(
            db,
            {
                "update_id": 900,
                "message": {
                    "from": {"id": 12345, "first_name": "Alex"},
                    "chat": {"id": 12345, "type": "private"},
                    "text": "Может ли кот водить такси?",
                },
            },
        )
    with patch(
        "app.worker.analyze",
        return_value=(
            simple_result(
                "nonsense",
                draft="В реальности котам права не выдают. В игре лучше посадить за руль персонажа!",
            ),
            [],
        ),
    ):
        run_once()
    with session_factory()() as db:
        ticket = db.scalar(select(Ticket))
        assert ticket.intake == "chat" and ticket.status == "in_progress"
    response = httpx.Response(200, json={"ok": True, "result": {"message_id": 44}})
    with patch("httpx.Client.post", return_value=response):
        run_once()
    with session_factory()() as db:
        assert db.scalar(select(Ticket)).status == "resolved"
        assert (
            db.scalar(select(Message).where(Message.author == "assistant")).delivery
            == "sent"
        )


def test_new_message_cancels_queued_auto_answer(connected):
    key = create_chat(demo=False)
    with patch("app.worker.analyze", return_value=(simple_result(), [])):
        run_once()
    with session_factory()() as db, db.begin():
        player_message(
            db, db.get(Ticket, key), "На самом деле я хочу пожаловаться на обман."
        )
    with patch("httpx.Client.post") as send:
        run_once()
        send.assert_not_called()
    with session_factory()() as db:
        assert (
            db.scalar(select(Message).where(Message.author == "assistant")).delivery
            == "cancelled"
        )


def test_auto_reply_flag_can_disable_all_automatic_sends(connected, monkeypatch):
    monkeypatch.setenv("AUTO_REPLY_ENABLED", "false")
    settings.cache_clear()
    key = create_chat()
    with patch("app.worker.analyze", return_value=(simple_result(), [])):
        run_once()
    with session_factory()() as db:
        assert db.get(Ticket, key).status == "review"
