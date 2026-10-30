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
    now,
)
from .schemas import DemoIn, LoginIn, MessageIn, RuleIn, TicketPatch
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

app = FastAPI(title="Grand Mobile Support Copilot", version="0.1.0")
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
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


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
    schedule_analysis(db, ticket)
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
    ticket = create_ticket(db, player, profile, data.text, data.category, demo=True)
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
