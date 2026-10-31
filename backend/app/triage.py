"""Shared processing entry point and token accounting. CRM has an explicit legacy adapter."""

from .config import settings


class TriageFailure(ValueError):
    """Safe error code only; provider payloads and secrets never enter errors."""

    def __init__(self, reason, *, provider_error=None, retry_after_seconds=None):
        super().__init__(reason)
        self.provider_error = provider_error or {}
        self.retry_after_seconds = retry_after_seconds


def pricing_snapshot(model):
    cfg = settings()
    # Standard short-context USD/1M snapshot, verified 2026-10-30. Unknown models require env rates.
    prices = {
        "gpt-6-luna": (0.10, 0.01, 0.50),
        "gpt-6.1-terra": (1.00, 0.05, 5.00),
        "gpt-6.1-sol": (2.00, 0.10, 10.00),
        "gpt-6-astra": (10.00, 1.00, 50.00),
    }
    known = prices.get(model)
    custom = (
        cfg.model_input_usd_per_million is not None
        or cfg.model_output_usd_per_million is not None
    )
    rates = (
        [
            cfg.model_input_usd_per_million,
            cfg.model_cached_input_usd_per_million,
            cfg.model_output_usd_per_million,
        ]
        if custom
        else known
    )
    write_rate = cfg.model_cache_write_usd_per_million
    if write_rate is None and known and not custom:
        write_rate = known[0] * 1.25  # omitted cache TTL defaults to 30m in our request
    return {
        "input": rates[0] if rates else None,
        "cached_input": rates[1] if rates else None,
        "output": rates[2] if rates else None,
        "cache_write": write_rate,
        "source": "env" if custom else "openai-standard-2026-10-30",
        "cache_write_ttl": "30m",
        "unit": "USD per 1M tokens",
    }


def token_cost(usage, model):
    prices = pricing_snapshot(model)
    rates = [prices["input"], prices["cached_input"], prices["output"]]
    if not usage or rates[0] is None or rates[2] is None:
        return None, "unpriced"
    details = usage.get("input_tokens_details") or {}
    cached = details.get("cached_tokens", 0)
    writes = details.get("cache_write_tokens", 0)
    if not isinstance(writes, int) or (writes and prices["cache_write"] is None):
        return None, "cache_write_price_required"
    if cached and rates[1] is None:
        return None, "cached_input_price_required"
    inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
    if (
        not isinstance(inputs, int)
        or not isinstance(outputs, int)
        or min(inputs, outputs, cached, writes) < 0
        or cached + writes > inputs
    ):
        return None, "unknown_usage"
    if prices["source"] != "env" and inputs > 272000:
        return None, "long_context_price_required"
    cost = (
        (inputs - cached - writes) * rates[0]
        + cached * (rates[1] or 0)
        + outputs * rates[2]
        + writes * (prices["cache_write"] or 0)
    ) / 1_000_000
    return round(cost, 10), prices["source"]


def run_triage(
    request, sources=None, *, run_id=None, duplicate=False, human_only=False
):
    from .contract import ContractRequest
    from .engine import from_legacy, run, to_legacy

    if isinstance(request, ContractRequest):
        return run(
            request, sources, run_id=run_id, duplicate=duplicate, human_only=human_only
        )
    canonical = from_legacy(request)
    return to_legacy(
        run(
            canonical,
            sources,
            run_id=run_id,
            duplicate=duplicate,
            human_only=human_only,
        ),
        canonical,
    )


def record_run(request, output, *, source, ticket_id=None, request_key=None):
    from .db import session_factory
    from .models import TriageRun

    data = output.model_dump(mode="json")
    official = data.get("contract")
    if "draft_reply" in data:
        official = output.public().model_dump(mode="json")
        data.update(
            id=output.ticket_id,
            language=output.lang,
            draft=output.draft_reply.text,
            human_reasons=output.reasons,
            summary=request.text[:350],
            claims=[],
        )
    if official:
        data["category"] = official["category"]
        data["priority"] = official["priority"]
        data["contract"] = official
    with session_factory()() as db, db.begin():
        db.add(
            TriageRun(
                id=output.telemetry["attempt_id"],
                request_key=request_key or output.telemetry["attempt_id"],
                run_id=output.telemetry["run_id"],
                ticket_id=ticket_id,
                source=source,
                provider=output.telemetry["provider"],
                model=output.telemetry["model"],
                language=data["language"],
                category=data["category"],
                needs_human=output.needs_human,
                status=output.status,
                latency_ms=output.telemetry["latency_ms"],
                cost_usd=output.telemetry["cost_usd"],
                input=request.model_dump(mode="json"),
                output=data,
            )
        )
    return output
