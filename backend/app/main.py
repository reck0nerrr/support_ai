from datetime import timedelta
import hmac
import re
import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, func, or_, select
from .config import settings
from .db import get_db
from .models import (
    Attachment,
    AuthSession,
    Job,
    LoginAttempt,
    Message,
    Player,
    Profile,
    Rule,
    Staff,
    Ticket,
    TriageRun,
    EvaluationRun,
    now,
)
from .schemas import (
    DemoIn,
    LoginIn,
    MessageIn,
    RuleIn,
    TicketPatch,
    EvaluationIn,
)
from .triage import run_triage, record_run
from .contract import ContractRequest, ContractResponse
from .dedup import recent_duplicate
from .evaluation import evaluate, runtime_summary
from .security import (
    COOKIE,
    DUMMY_PASSWORD_HASH,
    admin_staff,
    check_origin,
    create_session,
    current_staff,
    digest,
    ticket_access,
    verify_password,
)
from .services import (
    audit,
    create_ticket,
    enqueue,
    schedule_analysis,
    staff_dict,
    ticket_dict,
)
from .telegram import handle_update

app = FastAPI(title="Grand Mobile Support Copilot", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings().public_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api") or request.url.path == "/triage":
        response.headers["Cache-Control"] = "no-store"
    return response


@app.post(
    "/triage",
    response_model=ContractResponse,
    responses={502: {"model": ContractResponse}},
)
def triage(
    data: ContractRequest, request: Request, response: Response, db=Depends(get_db)
):
    key = settings().triage_api_key
    if key and not hmac.compare_digest(
        request.headers.get("authorization", ""), f"Bearer {key}"
    ):
        raise HTTPException(401, "Invalid triage API key")
    duplicate = recent_duplicate(db, data)
    db.rollback()
    output = record_run(data, run_triage(data, duplicate=duplicate), source="http")
    response.headers["X-Triage-Status"] = output.status
    response.headers["X-Triage-Latency-Ms"] = str(output.telemetry["latency_ms"])
    if output.telemetry["cost_usd"] is not None:
        response.headers["X-Triage-Cost-Usd"] = str(output.telemetry["cost_usd"])
    if output.error:
        response.headers["X-Triage-Error"] = output.error
    if output.status == "error":
        response.status_code = 502
    return output.public()


@app.get("/api/metrics")
def metrics(
    provider: str = "openai",
    source: str = "all",
    language: str = "all",
    run_id: str = "",
    days: int = Query(7, ge=1, le=90),
    staff=Depends(admin_staff),
    db=Depends(get_db),
):
    if (
        provider not in {"openai", "offline"}
        or source not in {"all", "http", "batch", "crm"}
        or language not in {"all", "ru", "en", "kk", "uz", "es", "pt"}
        or len(run_id) > 80
    ):
        raise HTTPException(422, "Invalid metrics filter")
    query = select(TriageRun).where(
        TriageRun.provider == provider,
        TriageRun.created_at >= now() - timedelta(days=days),
    )
    if source != "all":
        query = query.where(TriageRun.source == source)
    recent_ids = list(
        db.scalars(query.with_only_columns(TriageRun.run_id).distinct().limit(100))
    )
    if run_id:
        query = query.where(TriageRun.run_id == run_id)
    rows = db.scalars(
        query.order_by(TriageRun.created_at.desc(), TriageRun.id.desc()).limit(10001)
    ).all()
    truncated = len(rows) > 10000
    rows = rows[:10000]
    latest = {}
    for row in rows:
        latest.setdefault(row.request_key, row.output)
    if language != "all":
        latest = {k: v for k, v in latest.items() if v["language"] == language}
        rows = [r for r in rows if r.request_key in latest]
    requests = list(latest.values())
    return {
        "summary": runtime_summary(requests, attempts=[r.output for r in rows]),
        "by_language": {
            lang: runtime_summary(
                [p for p in requests if p["language"] == lang],
                attempts=[
                    r.output for r in rows if latest[r.request_key]["language"] == lang
                ],
            )
            for lang in sorted({p["language"] for p in requests})
        },
        "categories": {
            category: sum(
                p["category"] == category for p in requests if p["status"] == "ok"
            )
            for category in sorted(
                {p["category"] for p in requests if p["status"] == "ok"}
            )
        },
        "priorities": {
            p: sum(r.get("priority") == p for r in requests if r["status"] == "ok")
            for p in ("p0", "p1", "p2", "p3")
        },
        "duplicates_or_spam": sum(
            r.get(
                "is_spam_or_duplicate",
                (r.get("contract") or {}).get("is_spam_or_duplicate", False),
            )
            for r in requests
        ),
        "recent_runs": recent_ids,
        "days": days,
        "truncated": truncated,
        "generated_at": now(),
        "recent": [
            {
                "id": r.id,
                "created_at": r.created_at,
                "source": r.source,
                "external_id": r.output["id"],
                "language": r.language,
                "category": r.category,
                "needs_human": r.needs_human,
                "status": r.status,
                "latency_ms": r.latency_ms,
                "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                "error": r.output.get("error"),
            }
            for r in rows[:12]
        ],
    }


@app.get("/api/evaluations")
def evaluations(staff=Depends(admin_staff), db=Depends(get_db)):
    return [
        {
            "id": r.id,
            "name": r.name,
            "created_at": r.created_at,
            "dataset_kind": r.report["dataset_kind"],
            "n": r.report["counts"]["gold"],
            "macro_f1": r.report["classification"]["macro_f1"],
            "providers": r.report["runtime"]["providers"],
        }
        for r in db.scalars(
            select(EvaluationRun).order_by(EvaluationRun.created_at.desc()).limit(100)
        )
    ]


@app.get("/api/evaluations/{evaluation_id}")
def evaluation_detail(
    evaluation_id: str, staff=Depends(admin_staff), db=Depends(get_db)
):
    row = db.get(EvaluationRun, evaluation_id)
    if not row:
        raise HTTPException(404, "Evaluation not found")
    return row.report


@app.post("/api/evaluations")
def create_evaluation(
    data: EvaluationIn, staff=Depends(admin_staff), db=Depends(get_db)
):
    try:
        report = evaluate(
            data.gold,
            data.predictions,
            data.reviews,
            name=data.name,
            dataset_kind=data.dataset_kind,
        )
    except ValueError:
        raise HTTPException(
            422, "Проверьте уникальные id, разметку и формат файлов"
        ) from None
    row = EvaluationRun(name=data.name, report=report)
    db.add(row)
    audit(db, None, staff.name, "Рассчитана оценка: " + data.name)
    db.commit()
    return {"id": row.id, "report": report}


@app.get("/api/health")
def health(db=Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(data: LoginIn, request: Request, response: Response, db=Depends(get_db)):
    check_origin(request)
    ip = request.client.host if request.client else "unknown"
    cutoff = now() - timedelta(minutes=15)
    db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
    count = db.scalar(
        select(func.count())
        .select_from(LoginAttempt)
        .where(
            LoginAttempt.created_at >= cutoff,
            or_(LoginAttempt.ip == ip, LoginAttempt.login == data.login),
        )
    )
    if count >= 5:
        db.commit()
        raise HTTPException(429, "Слишком много попыток. Повторите через 15 минут.")
    staff = db.scalar(select(Staff).where(Staff.login == data.login))
    valid = verify_password(
        data.password, staff.password_hash if staff else DUMMY_PASSWORD_HASH
    )
    if not staff or not valid or not staff.active:
        db.add(LoginAttempt(ip=ip, login=data.login))
        db.commit()
        raise HTTPException(401, "Неверный логин или пароль")
    token, record = create_session(db, staff)
    db.commit()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="strict",
        max_age=settings().session_hours * 3600,
        path="/",
    )
    return {"staff": staff_dict(staff), "csrf": record.csrf}


@app.get("/api/auth/me")
def me(request: Request, staff=Depends(current_staff)):
    return {"staff": staff_dict(staff), "csrf": request.state.auth_session.csrf}


@app.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    staff=Depends(current_staff),
    db=Depends(get_db),
):
    db.execute(
        delete(AuthSession).where(
            AuthSession.token_hash == digest(request.cookies.get(COOKIE, ""))
        )
    )
    db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


def scope_query(staff):
    query = select(Ticket)
    if staff.role != "admin":
        query = query.join(Profile, Ticket.profile_id == Profile.id).where(
            Profile.server.in_(staff.servers)
        )
    return query


@app.get("/api/tickets")
def tickets(
    q: str = Query(default="", max_length=100),
    status: str = "",
    category: str = "",
    server: str = "",
    mine: bool = False,
    page: int = Query(default=1, ge=1, le=10000),
    staff=Depends(current_staff),
    db=Depends(get_db),
):
    query = scope_query(staff)
    if status:
        query = query.where(Ticket.status == status)
    if category:
        query = query.where(Ticket.category == category)
    if server:
        query = query.where(
            Ticket.profile_id.in_(select(Profile.id).where(Profile.server == server))
        )
    if mine:
        query = query.where(Ticket.assignee_id == staff.id)
    if q:
        query = query.where(
            or_(
                Ticket.title.icontains(q, autoescape=True),
                Ticket.id == (int(q) if q.isdigit() and len(q) < 10 else -1),
                Ticket.profile_id.in_(
                    select(Profile.id).where(
                        Profile.nickname.icontains(q, autoescape=True)
                    )
                ),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Ticket.updated_at.desc(), Ticket.id.desc())
        .offset((page - 1) * 30)
        .limit(30)
    ).all()
    return {
        "items": [ticket_dict(db, t) for t in rows],
        "total": total,
        "page": page,
        "page_size": 30,
    }


@app.get("/api/tickets/{ticket_id}")
def detail(ticket_id: int, staff=Depends(current_staff), db=Depends(get_db)):
    return ticket_dict(db, ticket_access(db, staff, ticket_id), detail=True)


@app.patch("/api/tickets/{ticket_id}")
def update_ticket(
    ticket_id: int, data: TicketPatch, staff=Depends(current_staff), db=Depends(get_db)
):
    ticket = ticket_access(db, staff, ticket_id, lock=True)
    if data.revision != ticket.revision:
        raise HTTPException(409, "Обращение изменилось. Обновите карточку.")
    fields = data.model_dump(exclude_unset=True, exclude={"revision"})
    if "status" in fields and fields["status"] in {"new", "analyzing"}:
        raise HTTPException(422, "Для повторного разбора используйте отдельную кнопку")
    if any(value is None for key, value in fields.items() if key != "assignee_id"):
        raise HTTPException(422, "Поле не может быть пустым")
    if "assignee_id" in fields and fields["assignee_id"]:
        target = db.get(Staff, fields["assignee_id"])
        profile = db.get(Profile, ticket.profile_id) if ticket.profile_id else None
        if (
            not target
            or not target.active
            or (
                target.role != "admin"
                and (not profile or profile.server not in target.servers)
            )
        ):
            raise HTTPException(422, "Сотруднику недоступен этот сервер")
        if staff.role == "operator" and target.id != staff.id:
            raise HTTPException(403, "Оператор может назначить обращение себе")
    for field, value in fields.items():
        setattr(ticket, field, value)
    if fields:
        ticket.revision += 1
        ticket.updated_at = now()
        audit(db, ticket.id, staff.name, "Изменены поля: " + ", ".join(fields))
    db.commit()
    return ticket_dict(db, ticket, detail=True)


@app.post("/api/tickets/{ticket_id}/messages")
def send_message(
    ticket_id: int, data: MessageIn, staff=Depends(current_staff), db=Depends(get_db)
):
    ticket = ticket_access(db, staff, ticket_id, lock=True)
    existing = db.scalar(select(Message).where(Message.request_key == data.request_key))
    if existing:
        if (
            existing.ticket_id != ticket_id
            or existing.staff_id != staff.id
            or existing.text != data.text
        ):
            raise HTTPException(409, "Ключ запроса уже использован")
        return ticket_dict(db, ticket, detail=True)
    if data.revision != ticket.revision:
        raise HTTPException(
            409, "Обращение изменилось. Проверьте новые сообщения перед отправкой."
        )
    player = db.get(Player, ticket.player_id)
    if not data.internal and not ticket.demo and not settings().telegram_bot_token:
        raise HTTPException(503, "Telegram-бот не настроен; ответ не отправлен")
    message = Message(
        ticket_id=ticket.id,
        author="note" if data.internal else "staff",
        staff_id=staff.id,
        text=data.text,
        delivery=None if data.internal else ("demo" if ticket.demo else "queued"),
        request_key=data.request_key,
    )
    db.add(message)
    db.flush()
    if not data.internal and not ticket.demo:
        enqueue(
            db,
            "telegram",
            {
                "ticket_id": ticket.id,
                "message_id": message.id,
                "chat_id": player.telegram_id,
                "text": f"Обращение #{ticket.id}\n\n{data.text}",
            },
            f"send:{message.id}",
        )
    ticket.revision += 1
    ticket.updated_at = now()
    if not data.internal:
        ticket.status = "in_progress"
    audit(
        db,
        ticket.id,
        staff.name,
        "Добавлен внутренний комментарий"
        if data.internal
        else (
            "Ответ сохранён в демо"
            if ticket.demo
            else "Ответ утверждён и поставлен на отправку"
        ),
    )
    db.commit()
    return ticket_dict(db, ticket, detail=True)


@app.post("/api/tickets/{ticket_id}/analyze")
def retry_analysis(ticket_id: int, staff=Depends(current_staff), db=Depends(get_db)):
    ticket = ticket_access(db, staff, ticket_id, lock=True)
    if db.scalar(
        select(Job).where(
            Job.kind == "analyze",
            Job.payload["ticket_id"].as_integer() == ticket.id,
            Job.state.in_(["pending", "running"]),
        )
    ):
        raise HTTPException(409, "Разбор уже выполняется")
    ticket.revision += 1
    ticket.content_revision += 1
    ticket.updated_at = now()
    schedule_analysis(db, ticket, allow_auto=False)
    audit(db, ticket.id, staff.name, "Запрошен повторный разбор")
    db.commit()
    return ticket_dict(db, ticket, detail=True)


@app.post("/api/tickets/{ticket_id}/messages/{message_id}/retry")
def retry_delivery(
    ticket_id: int, message_id: str, staff=Depends(current_staff), db=Depends(get_db)
):
    ticket = ticket_access(db, staff, ticket_id, lock=True)
    message = db.get(Message, message_id)
    if not message or message.ticket_id != ticket.id or message.delivery != "failed":
        raise HTTPException(
            409, "Повтор доступен только после подтверждённой ошибки доставки"
        )
    job = db.scalar(
        select(Job).where(Job.dedupe_key == f"send:{message.id}").with_for_update()
    )
    if not job or job.state != "failed":
        raise HTTPException(409, "Нельзя повторить отправку")
    job.state, job.available_at, job.error = "pending", now(), None
    message.delivery = "queued"
    audit(db, ticket.id, staff.name, "Повторная отправка после ошибки")
    db.commit()
    return ticket_dict(db, ticket, detail=True)


@app.get("/api/staff")
def staff_list(staff=Depends(current_staff), db=Depends(get_db)):
    return [
        staff_dict(s)
        for s in db.scalars(
            select(Staff).where(Staff.active.is_(True)).order_by(Staff.name)
        )
    ]


@app.get("/api/rules")
def rules(staff=Depends(current_staff), db=Depends(get_db)):
    return [
        {
            "id": r.id,
            "title": r.title,
            "clause": r.clause,
            "text": r.text,
            "url": r.url,
            "version": r.version,
            "language": r.language,
            "server": r.server,
            "approved": r.approved,
        }
        for r in db.scalars(select(Rule).order_by(Rule.created_at.desc()))
    ]


@app.post("/api/rules")
def add_rule(data: RuleIn, staff=Depends(admin_staff), db=Depends(get_db)):
    values = data.model_dump()
    values["url"] = str(data.url)
    rule = Rule(**values)
    db.add(rule)
    audit(db, None, staff.name, "Добавлена редакция правила: " + data.title)
    db.commit()
    return {"id": rule.id}


@app.patch("/api/rules/{rule_id}")
def approve_rule(
    rule_id: str, data: dict, staff=Depends(admin_staff), db=Depends(get_db)
):
    if set(data) != {"approved"} or not isinstance(data["approved"], bool):
        raise HTTPException(
            422, "Можно изменить только approved; текст меняется новой редакцией"
        )
    rule = db.get(Rule, rule_id)
    if not rule:
        raise HTTPException(404, "Правило не найдено")
    rule.approved = data["approved"]
    audit(db, None, staff.name, f"Правило {rule.id}: approved={rule.approved}")
    db.commit()
    return {"ok": True}


@app.get("/api/system")
def system(staff=Depends(current_staff), db=Depends(get_db)):
    servers = (
        list(db.scalars(select(Profile.server).distinct()))
        if staff.role == "admin"
        else staff.servers
    )
    return {
        "ai_provider": settings().ai_provider,
        "telegram_configured": bool(settings().telegram_bot_token),
        "demo_enabled": settings().demo_enabled,
        "auto_reply_enabled": settings().auto_reply_enabled,
        "profile_verification": "unavailable",
        "servers": sorted(servers),
        "failed_jobs": db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.state.in_(["failed", "uncertain"]))
        )
        if staff.role == "admin"
        else None,
    }


@app.post("/api/demo/tickets")
def demo_ticket(data: DemoIn, staff=Depends(admin_staff), db=Depends(get_db)):
    if not settings().demo_enabled:
        raise HTTPException(404)
    player = Player(name=data.nickname, language=data.language)
    db.add(player)
    db.flush()
    profile = Profile(player_id=player.id, server=data.server, nickname=data.nickname)
    db.add(profile)
    db.flush()
    ticket = create_ticket(
        db, player, profile, data.text, data.category, demo=True, intake=data.intake
    )
    db.commit()
    return ticket_dict(db, ticket, detail=True)


@app.post("/api/telegram/webhook")
async def webhook(request: Request, db=Depends(get_db)):
    secret = settings().telegram_webhook_secret
    if not secret or not hmac.compare_digest(
        request.headers.get("x-telegram-bot-api-secret-token", ""), secret
    ):
        raise HTTPException(403)
    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(413)
    try:
        import json

        update = json.loads(body)
        if not isinstance(update, dict):
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Invalid update")
    handle_update(db, update)
    db.commit()
    return {"ok": True}


@app.get("/api/attachments/{attachment_id}")
def attachment(attachment_id: str, staff=Depends(current_staff), db=Depends(get_db)):
    file = db.get(Attachment, attachment_id)
    if not file:
        raise HTTPException(404)
    ticket_access(db, staff, file.ticket_id)
    token = settings().telegram_bot_token
    if not token:
        raise HTTPException(503, "Telegram не настроен")
    try:
        with httpx.Client(timeout=30) as client:
            body = client.get(
                f"https://api.telegram.org/bot{token}/getFile",
                params={"file_id": file.file_id},
            ).json()
            path = body.get("result", {}).get("file_path", "")
            if (
                not body.get("ok")
                or not re.fullmatch(r"[a-zA-Z0-9_./-]+", path)
                or ".." in path
            ):
                raise ValueError()
            content = bytearray()
            with client.stream(
                "GET", f"https://api.telegram.org/file/bot{token}/{path}"
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 20 * 1024 * 1024:
                        raise ValueError()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Не удалось получить вложение")
    from urllib.parse import quote

    return Response(
        bytes(content),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''"
            + quote(file.name, safe="")
        },
    )
