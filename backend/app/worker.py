"""Run separately: python -m app.worker. PostgreSQL SKIP LOCKED supports multiple workers."""

import logging
import re
import time
from datetime import timedelta
import httpx
from sqlalchemy import select
from .ai import analyze
from .auto_reply import eligibility
from .config import settings
from .db import session_factory
from .models import Analysis, Job, Message, Player, Ticket, now
from .services import audit, enqueue
from .triage import TriageFailure

log = logging.getLogger("copilot.worker")
# Telegram Bot API URLs contain the bot token. httpx logs the full URL at INFO.
logging.getLogger("httpx").setLevel(logging.WARNING)


class TelegramNotConfigured(Exception):
    pass


def recover_stale(db):
    stale = db.scalars(
        select(Job)
        .where(Job.state == "running", Job.locked_at < now() - timedelta(minutes=5))
        .with_for_update(skip_locked=True)
    ).all()
    for job in stale:
        job.state = "uncertain" if job.kind == "telegram" else "pending"
        job.error = "worker_interrupted"
        if job.kind == "telegram" and job.payload.get("message_id"):
            message = db.get(Message, job.payload["message_id"])
            if message:
                message.delivery = "uncertain"
            if job.payload.get("automatic"):
                db.get(Ticket, job.payload["ticket_id"]).status = "review"


def claim():
    with session_factory()() as db, db.begin():
        recover_stale(db)
        job = db.scalar(
            select(Job)
            .where(Job.state == "pending", Job.available_at <= now())
            .order_by(Job.available_at, Job.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if not job:
            return None
        job.state, job.locked_at = "running", now()
        job.attempts += 1
        return job.id


def process(job_id):
    with session_factory()() as db:
        job = db.get(Job, job_id)
        if not job or job.state != "running":
            return
        try:
            if job.kind == "analyze":
                ticket = db.get(Ticket, job.payload["ticket_id"])
                if ticket.content_revision == job.payload["revision"]:
                    before_revision = ticket.revision
                    result, sources = analyze(db, ticket)
                    # Release the read transaction before locking: new player messages may arrive during inference.
                    db.rollback()
                    ticket = db.scalar(
                        select(Ticket)
                        .where(Ticket.id == job.payload["ticket_id"])
                        .with_for_update()
                    )
                    job = db.get(Job, job_id)
                    if ticket.content_revision == job.payload["revision"]:
                        automatic, reason = eligibility(db, ticket, result)
                        if ticket.revision != before_revision or not job.payload.get(
                            "allow_auto", False
                        ):
                            automatic, reason = (
                                False,
                                "Сотрудник изменил обращение или запросил ручной разбор",
                            )
                        result["routing"] = {
                            "mode": "automatic" if automatic else "human",
                            "reason": reason,
                        }
                        db.add(
                            Analysis(
                                ticket_id=ticket.id,
                                revision=ticket.content_revision,
                                provider=settings().ai_provider,
                                result=result,
                                sources=sources,
                            )
                        )
                        ticket.status = "review"
                        if ticket.revision == before_revision:
                            ticket.category = result["category"]
                            if result.get("triage"):
                                ticket.priority = (
                                    "high"
                                    if result["triage"]["priority"] in {"p0", "p1"}
                                    else "normal"
                                )
                        ticket.revision += 1
                        if automatic:
                            reply = Message(
                                ticket_id=ticket.id,
                                author="assistant",
                                text=result["draft"],
                                delivery="demo" if ticket.demo else "queued",
                                request_key=f"auto-{ticket.id}-{ticket.content_revision}",
                            )
                            db.add(reply)
                            db.flush()
                            if not ticket.demo:
                                player = db.get(Player, ticket.player_id)
                                enqueue(
                                    db,
                                    "telegram",
                                    {
                                        "ticket_id": ticket.id,
                                        "message_id": reply.id,
                                        "chat_id": player.telegram_id,
                                        "text": f"Support Copilot · #{ticket.id}\n\n{reply.text}",
                                        "automatic": True,
                                        "content_revision": ticket.content_revision,
                                        "ticket_revision": ticket.revision,
                                    },
                                    f"send:{reply.id}",
                                )
                            ticket.status = "resolved" if ticket.demo else "in_progress"
                            audit(
                                db,
                                ticket.id,
                                "Support Copilot",
                                "Подготовлен и сохранён автоматический ответ: "
                                + reason,
                            )
                        else:
                            audit(
                                db,
                                ticket.id,
                                "Support Copilot",
                                "Разбор подготовлен; требуется проверка сотрудником",
                            )
                job.state = "done"
            elif job.kind == "telegram":
                payload = job.payload
                if payload.get("automatic"):
                    ticket = db.get(Ticket, payload["ticket_id"])
                    if (
                        ticket.content_revision != payload["content_revision"]
                        or ticket.revision
                        != payload.get("ticket_revision", ticket.revision)
                        or ticket.assignee_id
                    ):
                        job.state = "cancelled"
                        db.get(Message, payload["message_id"]).delivery = "cancelled"
                        audit(
                            db,
                            ticket.id,
                            "Support Copilot",
                            "Автоответ отменён: появились новые данные или подключился сотрудник",
                        )
                        db.commit()
                        return
                if not settings().telegram_bot_token:
                    raise TelegramNotConfigured()
                # Telegram sendMessage has no idempotency key. Retry only explicit retryable rejections.
                with httpx.Client(timeout=25) as client:
                    response = client.post(
                        f"https://api.telegram.org/bot{settings().telegram_bot_token}/sendMessage",
                        json={
                            "chat_id": payload["chat_id"],
                            "text": payload["text"],
                            "link_preview_options": {"is_disabled": True},
                        },
                    )
                body = response.json()
                if body.get("ok"):
                    job.state = "done"
                    if payload.get("message_id"):
                        message = db.get(Message, payload["message_id"])
                        message.delivery = "sent"
                        message.telegram_message_id = body["result"]["message_id"]
                        audit(db, payload["ticket_id"], "Telegram", "Ответ доставлен")
                        if payload.get("automatic"):
                            ticket = db.scalar(
                                select(Ticket)
                                .where(Ticket.id == payload["ticket_id"])
                                .with_for_update()
                            )
                            if (
                                ticket.content_revision == payload["content_revision"]
                                and not ticket.assignee_id
                            ):
                                ticket.status = "resolved"
                                ticket.revision += 1
                elif response.status_code == 429:
                    job.state = "pending"
                    job.available_at = now() + timedelta(
                        seconds=min(
                            int(body.get("parameters", {}).get("retry_after", 30)), 3600
                        )
                    )
                    job.error = "telegram_rate_limit"
                else:
                    job.state, job.error = "failed", "telegram_rejected"
                    if payload.get("message_id"):
                        db.get(Message, payload["message_id"]).delivery = "failed"
                    if payload.get("automatic"):
                        db.get(Ticket, payload["ticket_id"]).status = "review"
            else:
                raise ValueError("unknown_job")
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            if not job:
                return
            # Never persist/log exception strings: HTTP exceptions can contain bot/API tokens.
            job.error = type(exc).__name__
            if isinstance(exc, TriageFailure) and re.fullmatch(
                r"[a-z0-9_]{1,90}", str(exc)
            ):
                job.error = str(exc)
            if job.kind == "telegram":
                job.state = (
                    "failed"
                    if isinstance(
                        exc,
                        (
                            httpx.ConnectError,
                            httpx.ConnectTimeout,
                            TelegramNotConfigured,
                        ),
                    )
                    else "uncertain"
                )
                if job.payload.get("message_id"):
                    db.get(Message, job.payload["message_id"]).delivery = job.state
                if job.payload.get("automatic"):
                    db.get(Ticket, job.payload["ticket_id"]).status = "review"
            else:
                provider_error = (
                    exc.provider_error if isinstance(exc, TriageFailure) else {}
                )
                error_code = provider_error.get("code")
                quota_exhausted = isinstance(exc, TriageFailure) and (
                    provider_error.get("limit_scope") == "day"
                    or provider_error.get("type") == "insufficient_quota"
                    or error_code
                    in {
                        "insufficient_quota",
                        "credit_balance_exhausted",
                        "organization_spend_limit_exceeded",
                        "project_spend_limit_exceeded",
                        "organization_usage_limit_exceeded",
                    }
                )
                if quota_exhausted:
                    job.error = (
                        "provider_daily_quota_exhausted"
                        if provider_error.get("limit_scope") == "day"
                        else "provider_billing_quota_exhausted"
                    )
                invalid_output = isinstance(exc, TriageFailure) and str(exc) in {
                    "invalid_model_response",
                    "incomplete_model_response",
                    "empty_or_refused_response",
                    "wrong_category_kind",
                    "wrong_reply_language",
                    "unknown_rule_reference",
                    "missing_draft_reference",
                    "unsupported_clause",
                    "model_provided_url",
                    "unsafe_draft_claim",
                    "handout_not_loaded",
                }
                job.state = (
                    "failed"
                    if quota_exhausted or invalid_output or job.attempts >= 3
                    else "pending"
                )
                delay = (
                    exc.retry_after_seconds if isinstance(exc, TriageFailure) else None
                )
                job.available_at = now() + timedelta(
                    seconds=max(delay or 0, 15 * job.attempts)
                )
                if job.state == "failed":
                    ticket = db.get(Ticket, job.payload["ticket_id"])
                    if ticket and ticket.content_revision == job.payload["revision"]:
                        ticket.status = "review"
                        audit(
                            db,
                            ticket.id,
                            "Support Copilot",
                            "AI недоступен: обращение передано сотруднику",
                        )
            db.commit()
            log.warning("Job %s ended with %s", job_id, job.error)


def run_once():
    job_id = claim()
    if job_id:
        process(job_id)
    return bool(job_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    while True:
        if not run_once():
            time.sleep(1)
