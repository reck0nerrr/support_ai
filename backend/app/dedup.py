"""Exact normalized repeats by the same reporter, within one hour."""

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import re

from .languages import normalize_kazakh


def fingerprint(request):
    text = normalize_kazakh(request.text, request.server_lang).lower()
    text = re.sub(r"\s+", " ", text).strip()
    # New evidence, nicknames, numbers and the accused must not disappear in normalization.
    value = (
        request.kind,
        text,
        request.reported_hash,
        request.reported_nick,
        request.server,
        request.evidence_count,
    )
    return hashlib.sha256(repr(value).encode()).hexdigest()


class BatchDuplicates:
    def __init__(self):
        self.seen = defaultdict(list)

    def check(self, request):
        if not request.reporter_hash or not request.created_at:
            return False
        ts = request.created_at.replace(
            tzinfo=request.created_at.tzinfo or timezone.utc
        ).timestamp()
        key = (request.reporter_hash, fingerprint(request))
        records = self.seen[key]
        duplicate = any(abs(ts - prior) <= 3600 for prior in records)
        records.append(ts)
        return duplicate


def recent_duplicate(db, request):
    if not request.reporter_hash:
        return False
    from datetime import timedelta
    from sqlalchemy import select
    from .contract import ContractRequest
    from .models import TriageRun

    rows = db.scalars(
        select(TriageRun)
        .where(
            TriageRun.source == "http",
            TriageRun.created_at >= datetime.now(timezone.utc) - timedelta(hours=1),
            TriageRun.input["reporter_hash"].as_string() == request.reporter_hash,
        )
        .order_by(TriageRun.created_at.desc())
        .limit(500)
    )
    target = fingerprint(request)
    for row in rows:
        previous = ContractRequest.model_validate(row.input)
        if request.ticket_id is not None and request.ticket_id == previous.ticket_id:
            continue
        if fingerprint(previous) == target:
            return True
    return False
