from datetime import timedelta
from unittest.mock import patch
import httpx
from sqlalchemy import func, select
from app import ai
from app.config import settings
from app.db import session_factory
from app.models import Attachment, Job, Message, Player, Ticket, now
from app.services import enqueue, player_message
from app.telegram import handle_update
from app.worker import claim, run_once


def relogin(client, login):
    response = client.post(
        "/api/auth/login", json={"login": login, "password": "TestPassword-123!"}
    )
    assert response.status_code == 200
    client.headers["x-csrf-token"] = response.json()["csrf"]


def test_session_csrf_and_logout(admin):
    token = admin.cookies.get("copilot_session")
    response = admin.get("/api/auth/me")
    assert response.status_code == 200
    assert "password" not in response.text
    assert (
        admin.post("/api/auth/logout", headers={"x-csrf-token": "bad"}).status_code
        == 403
    )
    assert (
        admin.post(
            "/api/auth/logout", headers={"origin": "https://attacker.example"}
        ).status_code
        == 403
    )
    assert admin.post("/api/auth/logout").status_code == 200
    admin.cookies.set("copilot_session", token)
    assert admin.get("/api/tickets").status_code == 401


def test_login_rate_limit_and_unauthorized(client):
    assert client.get("/api/tickets").status_code == 401
    for _ in range(5):
        assert (
            client.post(
                "/api/auth/login", json={"login": "admin", "password": "wrong"}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"login": "admin", "password": "TestPassword-123!"}
        ).status_code
        == 429
    )


def test_server_scope_and_admin_actions(admin, complaint):
    with session_factory()() as db, db.begin():
        file = Attachment(ticket_id=complaint["id"], name="proof.jpg", file_id="fake")
        db.add(file)
        db.flush()
        attachment_id = file.id
    relogin(admin, "other")
    assert admin.get("/api/tickets").json()["total"] == 0
    assert admin.get(f"/api/tickets/{complaint['id']}").status_code == 404
    assert admin.get(f"/api/attachments/{attachment_id}").status_code == 404
    assert (
        admin.post(
            "/api/demo/tickets",
            json={
                "nickname": "Test_Player",
                "server": "Сервер 02",
                "text": "Случилась ошибка в игре",
            },
        ).status_code
        == 403
    )
    relogin(admin, "operator")
    assert admin.get("/api/tickets").json()["total"] == 1
    assert admin.get(f"/api/tickets/{complaint['id']}").status_code == 200


def test_offline_analysis_survives_assignment(admin, complaint):
    staff_id = admin.get("/api/auth/me").json()["staff"]["id"]
    assert (
        admin.patch(
            f"/api/tickets/{complaint['id']}",
            json={"revision": complaint["revision"], "assignee_id": staff_id},
        ).status_code
        == 200
    )
    assert run_once()
    ticket = admin.get(f"/api/tickets/{complaint['id']}").json()
    assert ticket["status"] == "review"
    assert ticket["analysis"]["provider"] == "offline"
    assert not ticket["analysis"]["stale"]
    assert ticket["analysis"]["result"]["verified_facts"] == []
    assert ticket["analysis"]["result"]["escalation_reasons"]


def test_response_is_idempotent_and_notes_private(admin, complaint):
    body = {
        "revision": complaint["revision"],
        "text": "Пожалуйста, уточните время события.",
        "internal": False,
        "request_key": "unique-request-key-00001",
    }
    result = admin.post(f"/api/tickets/{complaint['id']}/messages", json=body)
    assert result.status_code == 200
    repeated = admin.post(f"/api/tickets/{complaint['id']}/messages", json=body)
    assert repeated.status_code == 200
    assert len(repeated.json()["messages"]) == 2
    assert repeated.json()["messages"][-1]["delivery"] == "demo"
    stale = {**body, "request_key": "unique-request-key-00002"}
    assert (
        admin.post(f"/api/tickets/{complaint['id']}/messages", json=stale).status_code
        == 409
    )
    current = repeated.json()
    note = {
        "revision": current["revision"],
        "text": "Проверить журнал обменов",
        "internal": True,
        "request_key": "unique-request-key-00003",
    }
    assert (
        admin.post(f"/api/tickets/{complaint['id']}/messages", json=note).json()[
            "messages"
        ][-1]["author"]
        == "note"
    )
    with session_factory()() as db:
        assert (
            db.scalar(
                select(func.count()).select_from(Job).where(Job.kind == "telegram")
            )
            == 0
        )


def test_unapproved_rules_are_not_retrieved(admin, complaint):
    data = {
        "title": "Правила обмена",
        "text": "Жалоба на обмен автомобилями требует проверки обстоятельств и доказательств.",
        "url": "https://support.grnd.gg/ru/articles/11071809",
        "version": "test",
    }
    key = admin.post("/api/rules", json=data).json()["id"]
    with session_factory()() as db:
        assert ai.retrieve_rules(db, complaint["title"], "Сервер 01") == []
    assert admin.patch(f"/api/rules/{key}", json={"approved": True}).status_code == 200
    with session_factory()() as db:
        assert len(ai.retrieve_rules(db, complaint["title"], "Сервер 01")) == 1
    relogin(admin, "operator")
    assert admin.patch(f"/api/rules/{key}", json={"approved": False}).status_code == 403


def test_new_player_message_invalidates_analysis(admin, complaint):
    run_once()
    with session_factory()() as db, db.begin():
        ticket = db.get(Ticket, complaint["id"])
        player_message(db, ticket, "Уточнение: событие произошло вчера в 19:20.")
    assert admin.get(f"/api/tickets/{complaint['id']}").json()["analysis"]["stale"]
    run_once()
    current = admin.get(f"/api/tickets/{complaint['id']}").json()
    assert not current["analysis"]["stale"]
    assert "19:20" in current["analysis"]["result"]["summary"]


def test_ai_failure_keeps_ticket_and_escalates(admin, complaint):
    for _ in range(3):
        with session_factory()() as db, db.begin():
            job = db.scalar(select(Job).where(Job.kind == "analyze"))
            job.available_at = now() - timedelta(seconds=1)
        with patch(
            "app.worker.analyze",
            side_effect=ValueError("private API secret should never be persisted"),
        ):
            assert run_once()
    ticket = admin.get(f"/api/tickets/{complaint['id']}").json()
    assert ticket["status"] == "review" and ticket["messages"]
    assert ticket["jobs"][0]["state"] == "failed"
    assert ticket["jobs"][0]["error"] == "ValueError"
    assert "private API secret" not in str(ticket)


def update(number, text, user=12345, **extra):
    return {
        "update_id": number,
        "message": {
            "from": {"id": user, "first_name": "Alex", "language_code": "ru"},
            "chat": {"id": user, "type": "private"},
            "text": text,
            **extra,
        },
    }


def bot_send(number, text, user=12345, **extra):
    with session_factory()() as db, db.begin():
        return handle_update(db, update(number, text, user, **extra))


def test_bot_full_dialog_deduplication_and_private_history():
    for number, text in enumerate(
        [
            "/start",
            "/profile Сервер 01 | Alex_Walker",
            "/new",
            "1",
            "Меня обманули при обмене автомобилями вчера в 20:00.",
            "Ссылка на видео https://example.com/evidence",
            "/preview",
            "/send",
        ],
        start=1,
    ):
        assert bot_send(number, text)
    assert not bot_send(8, "/send")
    with session_factory()() as db, db.begin():
        assert db.scalar(select(func.count()).select_from(Ticket)) == 1
        ticket = db.scalar(select(Ticket))
        db.add(Message(ticket_id=ticket.id, author="note", text="INTERNAL_ONLY"))
        db.add(
            Message(
                ticket_id=ticket.id,
                author="staff",
                text="UNSENT_REPLY",
                delivery="queued",
            )
        )
        ticket_id = ticket.id
    bot_send(9, f"/ticket {ticket_id}")
    bot_send(10, f"/ticket {ticket_id}", user=999)
    with session_factory()() as db:
        jobs = db.scalars(
            select(Job).where(Job.kind == "telegram").order_by(Job.available_at)
        ).all()
        assert "INTERNAL_ONLY" not in str([j.payload for j in jobs])
        assert "UNSENT_REPLY" not in str([j.payload for j in jobs])
        assert jobs[-1].payload["text"] == "Обращение не найдено."
        assert db.scalar(select(Ticket)).profile_id


def test_recovery_without_profile_and_appeal_link():
    for n, t in enumerate(
        [
            "/new",
            "4",
            "Потерял доступ к персонажу и не могу войти в аккаунт.",
            "/preview",
            "/send",
        ],
        start=100,
    ):
        bot_send(n, t)
    with session_factory()() as db:
        ticket = db.scalar(select(Ticket))
        assert ticket.profile_id is None
        original = ticket.id
    for n, t in enumerate(
        [
            "/new",
            "3",
            str(original),
            "Прошу повторно рассмотреть моё обращение об аккаунте.",
            "/preview",
            "/send",
        ],
        start=110,
    ):
        bot_send(n, t)
    with session_factory()() as db:
        appeal = db.scalar(select(Ticket).where(Ticket.category == "appeal"))
        assert appeal.parent_id == original


def test_webhook_requires_secret(admin, monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret")
    settings.cache_clear()
    assert (
        admin.post("/api/telegram/webhook", json=update(1, "/start")).status_code == 403
    )
    assert (
        admin.post(
            "/api/telegram/webhook",
            json=update(1, "/start"),
            headers={"x-telegram-bot-api-secret-token": "test-secret"},
        ).status_code
        == 200
    )


def test_uncertain_delivery_is_not_retried(admin, complaint, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-bot-token")
    settings.cache_clear()
    with session_factory()() as db, db.begin():
        ticket = db.get(Ticket, complaint["id"])
        ticket.demo = False
        player = db.get(Player, ticket.player_id)
        player.telegram_id = 12345
    result = admin.post(
        f"/api/tickets/{complaint['id']}/messages",
        json={
            "revision": complaint["revision"],
            "text": "Ответ сотрудника",
            "request_key": "delivery-test-key-0001",
        },
    )
    assert result.status_code == 200
    with session_factory()() as db, db.begin():
        db.scalar(select(Job).where(Job.kind == "analyze")).state = "done"
    with patch("httpx.Client.post", side_effect=httpx.ReadTimeout("uncertain")):
        assert run_once()
    assert not run_once()
    current = admin.get(f"/api/tickets/{complaint['id']}").json()
    message = next(m for m in current["messages"] if m["author"] == "staff")
    assert message["delivery"] == "uncertain"
    assert (
        admin.post(
            f"/api/tickets/{complaint['id']}/messages/{message['id']}/retry"
        ).status_code
        == 409
    )


def test_interrupted_delivery_is_not_automatically_retried():
    with session_factory()() as db, db.begin():
        job = enqueue(db, "telegram", {"chat_id": 12345, "text": "hello"})
        db.flush()
        job.state = "running"
        job.locked_at = now() - timedelta(minutes=10)
        key = job.id
    assert claim() is None
    with session_factory()() as db:
        assert db.get(Job, key).state == "uncertain"


def test_model_references_are_validated(admin, complaint, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    settings.cache_clear()
    import json

    result = {
        "language": "ru",
        "category": "player",
        "summary": "Требуется проверка",
        "claims": ["Обман"],
        "verified_facts": ["Выдуманный факт"],
        "missing": [],
        "escalation_reasons": ["Проверить"],
        "rule_ids": ["invented"],
        "draft": "Здравствуйте",
    }
    response = httpx.Response(
        200,
        json={
            "status": "completed",
            "output": [
                {"content": [{"type": "output_text", "text": json.dumps(result)}]}
            ],
        },
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    with session_factory()() as db, patch("httpx.Client.post", return_value=response):
        import pytest

        with pytest.raises(ValueError, match="unknown_rule_reference"):
            ai.analyze(db, db.get(Ticket, complaint["id"]))


def test_job_claim_is_exclusive():
    with session_factory()() as db, db.begin():
        enqueue(db, "analyze", {"ticket_id": 0, "revision": 1})
        enqueue(db, "analyze", {"ticket_id": 0, "revision": 2})
    first, second = claim(), claim()
    assert first and second and first != second and claim() is None


def test_empty_message_and_unsafe_origin(admin, complaint):
    path = f"/api/tickets/{complaint['id']}/messages"
    data = {
        "revision": complaint["revision"],
        "text": "   ",
        "request_key": "blank-message-key-0001",
    }
    assert admin.post(path, json=data).status_code == 422
    assert (
        admin.post(
            path,
            json={**data, "text": "Текст"},
            headers={"origin": "https://evil.example"},
        ).status_code
        == 403
    )
