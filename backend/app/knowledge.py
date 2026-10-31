"""Small, versioned official-source corpus; no runtime scraping or vector service."""

import hashlib
import json
from pathlib import Path

CORPUS_PATH = Path(__file__).parent / "data" / "rules.json"


def bundled_rules(server="*"):
    from .handout import load_rules

    try:
        return load_rules()
    except FileNotFoundError:
        pass
    data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    return [r for r in data["rules"] if r.get("server", "*") in {"*", server}]


def corpus_version(rules):
    return hashlib.sha256(
        json.dumps(rules, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def database_rules(db, server):
    from sqlalchemy import select
    from .models import Rule

    return [
        {
            key: getattr(r, key)
            for key in ("id", "title", "clause", "url", "version", "text")
        }
        for r in db.scalars(
            select(Rule)
            .where(Rule.approved.is_(True), Rule.server.in_(["*", server]))
            .order_by(Rule.id)
        )
    ]


def active_crm_rules(db, server):
    """DB approval overrides a bundled rule with the same stable id."""
    from sqlalchemy import select
    from .models import Rule

    result = {r["id"]: r for r in bundled_rules(server)}
    official = any(r.get("version", "").startswith("handout-") for r in result.values())
    for row in db.scalars(
        select(Rule).where(Rule.server.in_(["*", server])).order_by(Rule.id)
    ):
        if official and row.id.startswith("gm-"):
            continue
        if row.approved:
            result[row.id] = {
                **result.get(row.id, {}),
                **{
                    k: getattr(row, k)
                    for k in ("id", "title", "clause", "url", "version", "text")
                },
            }
        else:
            result.pop(row.id, None)
    return list(result.values())


def validate_corpus(rules):
    ids = [r["id"] for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_rule_id")
    # Never silently truncate a rule or omit a section for a different language.
    if len(json.dumps(rules, ensure_ascii=False)) > 1_000_000:
        raise ValueError("corpus_too_large")
    return rules
