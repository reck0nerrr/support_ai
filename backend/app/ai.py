"""CRM adapter around the same triage engine used by HTTP and JSONL."""

from sqlalchemy import select
from .knowledge import active_crm_rules, database_rules
from .models import Attachment, Message, Player, Profile
from .schemas import TriageRequest
from .triage import TriageFailure, record_run, run_triage


def retrieve_rules(db, text, server):
    # The curated corpus is small: give the model the entire applicable set, in any language.
    return database_rules(db, server)


def analyze(db, ticket):
    player = db.get(Player, ticket.player_id)
    profile = db.get(Profile, ticket.profile_id) if ticket.profile_id else None
    texts = list(
        db.scalars(
            select(Message.text)
            .where(Message.ticket_id == ticket.id, Message.author == "player")
            .order_by(Message.created_at, Message.id)
        )
    )
    attachment_count = len(
        db.scalars(select(Attachment).where(Attachment.ticket_id == ticket.id)).all()
    )
    request = TriageRequest(
        id=ticket.id,
        text="\n".join(texts)[-24000:],
        language=player.language
        if player.language in {"ru", "en", "kk", "uz"}
        else "auto",
        server=profile.server if profile else "*",
        intake=ticket.intake,
        attachments_count=attachment_count,
    )
    sources = active_crm_rules(db, request.server)
    ticket_id, revision = ticket.id, ticket.content_revision
    # Don't hold a read transaction while an external model works or telemetry commits.
    db.rollback()
    output = run_triage(
        request, sources, run_id=f"crm-{ticket_id}", human_only=attachment_count > 0
    )
    record_run(
        request,
        output,
        source="crm",
        ticket_id=ticket_id,
        request_key=f"crm:{ticket_id}:{revision}",
    )
    if output.error:
        raise TriageFailure(
            output.error,
            provider_error=output.telemetry.get("provider_error"),
            retry_after_seconds=output.telemetry.get("retry_after_seconds"),
        )
    return {
        "language": output.language,
        "category": output.category,
        "summary": output.summary,
        "claims": output.claims,
        "verified_facts": [],
        "missing": output.missing_fields,
        "escalation_reasons": output.human_reasons,
        "rule_ids": [c.id for c in output.citations],
        "draft": output.draft,
        "intent": output.intent,
        "auto_reply_safe": not output.needs_human,
        "requires_account_access": output.needs_human,
        "needs_human": output.needs_human,
        "telemetry": output.telemetry,
        "triage": output.contract,
    }, [s for s in sources if s["id"] in set(output.telemetry.get("retrieved_ids", []))]
