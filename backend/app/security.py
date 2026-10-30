import hashlib
import hmac
import secrets
from datetime import timedelta
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .config import settings
from .db import get_db
from .models import AuthSession, Staff, Ticket, Profile, now

COOKIE = "copilot_session"


def hash_password(password: str):
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return f"scrypt${salt}${key.hex()}"


def verify_password(password: str, encoded: str):
    try:
        _, salt, expected = encoded.split("$")
        actual = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1
        ).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = hash_password("timing-only-placeholder")


def digest(value: str):
    return hashlib.sha256(value.encode()).hexdigest()


def create_session(db, staff):
    token = secrets.token_urlsafe(32)
    record = AuthSession(
        token_hash=digest(token),
        staff_id=staff.id,
        csrf=secrets.token_hex(32),
        expires_at=now() + timedelta(hours=settings().session_hours),
    )
    db.add(record)
    return token, record


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin != settings().public_origin:
        raise HTTPException(403, "Недопустимый источник запроса")


def current_staff(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE, "")
    session = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == digest(token), AuthSession.expires_at > now()
        )
    )
    staff = db.get(Staff, session.staff_id) if session else None
    if not staff or not staff.active:
        raise HTTPException(401, "Войдите в систему")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        if not hmac.compare_digest(
            request.headers.get("x-csrf-token", ""), session.csrf
        ):
            raise HTTPException(403, "Недействительный CSRF-токен")
    request.state.auth_session = session
    return staff


def admin_staff(staff=Depends(current_staff)):
    if staff.role != "admin":
        raise HTTPException(403, "Доступно администратору")
    return staff


def ticket_access(db, staff, ticket_id, lock=False):
    query = select(Ticket).where(Ticket.id == ticket_id)
    if lock:
        query = query.with_for_update()
    ticket = db.scalar(query)
    if not ticket:
        raise HTTPException(404, "Обращение не найдено")
    profile = db.get(Profile, ticket.profile_id) if ticket.profile_id else None
    if staff.role != "admin" and (not profile or profile.server not in staff.servers):
        raise HTTPException(404, "Обращение не найдено")
    return ticket
