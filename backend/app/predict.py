"""Streaming organizer JSONL inference, with outcome labels and admin replies removed."""

import argparse
import gzip
import json
import math
from pathlib import Path
import sys
from time import perf_counter, sleep
import uuid

from pydantic import ValidationError
from .config import settings
from .contract import ContractRequest, Prediction, parse_export
from .dedup import BatchDuplicates
from .engine import base_decision, from_legacy
from .schemas import TriageRequest
from .triage import record_run, run_triage

QUOTA_CODES = {
    "insufficient_quota",
    "credit_balance_exhausted",
    "project_spend_limit_exceeded",
    "organization_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
}


def not_called(request, run_id, error, provider_error=None):
    decision = base_decision(request)
    decision.reasons = ["Автоматический разбор не выполнен: требуется сотрудник"]
    return Prediction(
        **decision.model_dump(),
        ticket_id=request.ticket_id,
        status="error",
        error=error,
        telemetry={
            "attempt_id": uuid.uuid4().hex,
            "run_id": run_id,
            "provider": settings().ai_provider,
            "model": "not_called",
            "latency_ms": 0,
            "llm_latency_ms": 0,
            "usage": {"input_tokens": 0, "output_tokens": 0},
            "cost_usd": 0.0,
            "pricing": "not_called",
            "called_provider": False,
            "batch_pacing_ms": 0,
            "provider_error": provider_error or {},
        },
    )


def predict(input_path, output_path, *, persist=False, run_id=None, rpm=None):
    input_path, output_path = Path(input_path), Path(output_path)
    if input_path.resolve() == output_path.resolve():
        raise ValueError("IN and OUT must differ")
    run_id = run_id or uuid.uuid4().hex
    if not 1 <= len(run_id) <= 80:
        raise ValueError("run_id must contain 1-80 characters")
    rpm = settings().predict_rpm if rpm is None else rpm
    if not math.isfinite(rpm) or not 0 <= rpm <= 600:
        raise ValueError("Invalid RPM")
    interval = 60 / rpm if rpm and settings().ai_provider == "openai" else 0
    next_start, blocked = 0, None
    blocked_reason = "provider_quota_exhausted"
    seen, duplicates = set(), BatchDuplicates()
    total = errors = 0
    opener = gzip.open if input_path.suffix == ".gz" else open
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        opener(input_path, "rt", encoding="utf-8-sig") as incoming,
        output_path.open("w", encoding="utf-8") as outgoing,
    ):
        for line_number, line in enumerate(incoming, 1):
            data = {}
            try:
                data = json.loads(line)
                # Developer convenience: older local synthetic fixtures remain readable.
                request = (
                    from_legacy(TriageRequest.model_validate(data))
                    if isinstance(data, dict)
                    and "text" in data
                    and "messages" not in data
                    else parse_export(data)
                )
                if request.ticket_id is None:
                    request.ticket_id = str(line_number)
                identity = json.dumps(request.ticket_id, ensure_ascii=False)
                if identity in seen:
                    raise ValueError("duplicate_id")
                seen.add(identity)
            except (json.JSONDecodeError, ValidationError, ValueError):
                identity = (
                    data.get("ticket_id", data.get("id"))
                    if isinstance(data, dict)
                    else None
                )
                if type(identity) not in (str, int):
                    identity = str(line_number)
                request = ContractRequest(
                    ticket_id=identity,
                    kind="report",
                    messages=[{"role": "player", "text": ""}],
                )
                output = not_called(request, run_id, "invalid_input")
            else:
                duplicate = duplicates.check(request)
                if blocked is not None:
                    output = not_called(request, run_id, blocked_reason, blocked)
                else:
                    pacing_started = perf_counter()
                    while (delay := next_start - perf_counter()) > 0:
                        sleep(min(delay, 30))
                    next_start = perf_counter() + interval
                    pacing_ms = round((perf_counter() - pacing_started) * 1000)
                    output = run_triage(request, run_id=run_id, duplicate=duplicate)
                    output.telemetry["batch_pacing_ms"] = pacing_ms
                    failure = output.telemetry.get("provider_error", {})
                    if (
                        failure.get("limit_scope") == "day"
                        or failure.get("code") in QUOTA_CODES
                        or failure.get("type") == "insufficient_quota"
                    ):
                        blocked = failure
                        print(
                            "Provider quota exhausted: remaining rows saved without API calls.",
                            file=sys.stderr,
                        )
                    elif output.error == "provider_http_429":
                        wait = output.telemetry.get("retry_after_seconds", 5)
                        if wait > settings().llm_retry_max_wait_seconds:
                            blocked, blocked_reason = failure, "provider_cooldown"
                            print(
                                "Provider cooldown exceeds the batch wait limit: remaining rows deferred without API calls.",
                                file=sys.stderr,
                            )
                        else:
                            next_start = max(next_start, perf_counter() + max(5, wait))
                if duplicate:
                    output.is_spam_or_duplicate = True
                if persist:
                    record_run(
                        request,
                        output,
                        source="batch",
                        request_key=f"{run_id}:{line_number}",
                    )
            outgoing.write(output.model_dump_json() + "\n")
            outgoing.flush()
            total += 1
            errors += output.status == "error"
    print(
        f"run_id={run_id} provider={settings().ai_provider} rows={total} errors={errors}",
        file=sys.stderr,
    )
    return 1 if errors else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--persist", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--rpm", type=float)
    args = parser.parse_args()
    try:
        raise SystemExit(
            predict(
                args.input,
                args.output,
                persist=args.persist,
                run_id=args.run_id,
                rpm=args.rpm,
            )
        )
    except (OSError, ValueError):
        print(
            "Prediction failed: check file paths, format and database configuration.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
