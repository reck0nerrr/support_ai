from sqlalchemy import select
from .models import (
    Analysis,
    Attachment,
    Audit,
    Job,
    Message,
    Player,
    Profile,
    Staff,
    Ticket,
    now,
)


def audit(db, ticket_id, actor, action):
    db.add(Audit(ticket_id=ticket_id, actor=actor, action=action))


def enqueue(db, kind, payload, key=None):
    job = Job(kind=kind, payload=payload, dedupe_key=key)
    db.add(job)
    return job


def schedule_analysis(db, ticket, allow_auto=True):
    ticket.status = "analyzing"
    enqueue(
        db,
        "analyze",
        {
            "ticket_id": ticket.id,
            "revision": ticket.content_revision,
            "allow_auto": allow_auto,
        },
        f"analysis:{ticket.id}:{ticket.content_revision}",
    )


def create_ticket(
    db,
    player,
    profile,
    text,
    category="other",
    parent_id=None,
    demo=False,
    attachments=None,
    intake="complaint",
):
    ticket = Ticket(
        player_id=player.id,
        profile_id=profile.id if profile else None,
        title=text[:120],
        category=category,
        parent_id=parent_id,
        demo=demo,
        intake=intake,
    )
    db.add(ticket)
    db.flush()
    db.add(Message(ticket_id=ticket.id, author="player", text=text))
    for file in attachments or []:
        db.add(Attachment(ticket_id=ticket.id, **file))
    schedule_analysis(db, ticket)
    audit(db, ticket.id, player.name, "Обращение создано")
    return ticket


def player_message(db, ticket, text, attachments=None):
    db.add(Message(ticket_id=ticket.id, author="player", text=text))
    for file in attachments or []:
        db.add(Attachment(ticket_id=ticket.id, **file))
    ticket.revision += 1
    ticket.content_revision += 1
    ticket.updated_at = now()
    schedule_analysis(db, ticket)
    audit(db, ticket.id, "Игрок", "Получено дополнение")


def profile_dict(profile):
    return (
        {
            "id": profile.id,
            "nickname": profile.nickname,
            "server": profile.server,
            "verified": profile.verified,
        }
        if profile
        else None
    )


def staff_dict(staff):
    return {
        "id": staff.id,
        "name": staff.name,
        "login": staff.login,
        "role": staff.role,
        "servers": staff.servers,
    }


def ticket_dict(db, ticket, detail=False):
    player = db.get(Player, ticket.player_id)
    profile = db.get(Profile, ticket.profile_id) if ticket.profile_id else None
    assignee = db.get(Staff, ticket.assignee_id) if ticket.assignee_id else None
    result = {
        "id": ticket.id,
        "title": ticket.title,
        "intake": ticket.intake,
        "category": ticket.category,
        "status": ticket.status,
        "priority": ticket.priority,
        "revision": ticket.revision,
        "demo": ticket.demo,
        "parent_id": ticket.parent_id,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "player": {"name": player.name, "language": player.language},
        "profile": profile_dict(profile),
        "assignee": staff_dict(assignee) if assignee else None,
    }
    if detail:
        result["messages"] = [
            {
                "id": m.id,
                "author": m.author,
                "text": m.text,
                "delivery": m.delivery,
                "created_at": m.created_at,
            }
            for m in db.scalars(
                select(Message)
                .where(Message.ticket_id == ticket.id)
                .order_by(Message.created_at, Message.id)
            )
        ]
        result["attachments"] = [
            {"id": a.id, "name": a.name, "size": a.size, "mime": a.mime}
            for a in db.scalars(
                select(Attachment).where(Attachment.ticket_id == ticket.id)
            )
        ]
        analysis = db.scalar(
            select(Analysis)
            .where(Analysis.ticket_id == ticket.id)
            .order_by(Analysis.created_at.desc(), Analysis.id.desc())
        )
        result["analysis"] = (
            {
                "id": analysis.id,
                "provider": analysis.provider,
                "revision": analysis.revision,
                "result": analysis.result,
                "sources": analysis.sources,
                "created_at": analysis.created_at,
                "stale": analysis.revision != ticket.content_revision,
            }
            if analysis
            else None
        )
        result["audit"] = [
            {"actor": a.actor, "action": a.action, "created_at": a.created_at}
            for a in db.scalars(
                select(Audit)
                .where(Audit.ticket_id == ticket.id)
                .order_by(Audit.created_at.desc(), Audit.id.desc())
                .limit(50)
            )
        ]
        result["jobs"] = [
            {
                "id": j.id,
                "kind": j.kind,
                "state": j.state,
                "attempts": j.attempts,
                "error": j.error,
            }
            for j in db.scalars(
                select(Job)
                .where(Job.payload["ticket_id"].as_integer() == ticket.id)
                .order_by(Job.available_at.desc())
                .limit(20)
            )
        ]
    return result
