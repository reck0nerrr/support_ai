"""Run separately: python -m app.worker. PostgreSQL SKIP LOCKED supports multiple workers."""

import logging
import time
from datetime import timedelta
import httpx
from sqlalchemy import select
from .ai import analyze
from .config import settings
from .db import session_factory
from .models import Analysis, Job, Message, Ticket, now
from .services import audit

log = logging.getLogger("copilot.worker")


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
                        ticket.revision += 1
                        audit(
                            db,
                            ticket.id,
                            "Support Copilot",
                            "Разбор подготовлен; требуется проверка сотрудником",
                        )
                job.state = "done"
            elif job.kind == "telegram":
                payload = job.payload
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
            else:
                job.state = "failed" if job.attempts >= 3 else "pending"
                job.available_at = now() + timedelta(seconds=15 * job.attempts)
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
