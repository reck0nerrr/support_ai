import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest

from app.config import settings
from app.contract import ContractRequest, ContractResponse, parse_export
from app.db import session_factory
from app.dedup import BatchDuplicates
from app.engine import base_decision
from app.evaluation import evaluate
from app.handout import load_rules
from app.languages import language_hint, normalize_kazakh
from app.models import Job, TriageRun
from app.predict import predict
from app.retrieval import retrieve
from app.triage import TriageFailure, record_run, run_triage, token_cost


def request(text="Arman_Test оскорбил меня", **kw):
    return ContractRequest(
        kind=kw.pop("kind", "complaint"),
        messages=[{"role": "player", "text": text}],
        **kw,
    )


def decision(req=None):
    req = req or request()
    result = base_decision(req).model_dump()
    result.update(
        confidence=0.9,
        needs_human=False,
        reasons=[],
        intent="complaint" if req.kind == "complaint" else "faq",
    )
    result["draft_reply"] = {
        "lang": result["lang"],
        "text": "Здравствуйте! По правилу [2.1] оскорбления запрещены. Указанные обстоятельства требуют проверки.",
        "cited": ["2.1"],
    }
    return result


@contextmanager
def model_reply(value=None, *, status=200, headers=None, exception=None):
    if status == 200:
        value = {
            "status": "completed",
            "model": "test",
            "usage": {"input_tokens": 2000, "output_tokens": 100},
            "output": [
                {
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(value or decision(), ensure_ascii=False),
                        }
                    ]
                }
            ],
        }
    response = httpx.Response(
        status,
        json=value,
        headers=headers,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )
    with patch("app.engine.httpx.Client") as cls:
        client = cls.return_value.__enter__.return_value
        if exception:
            client.post.side_effect = exception
        else:
            client.post.return_value = response
        yield client.post


@pytest.fixture
def connected(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    settings.cache_clear()


def test_exact_http_contract_and_persistence(client):
    response = client.post(
        "/triage",
        json={
            "kind": "complaint",
            "messages": [
                {"role": "player", "text": "Arman_Test оскорбляет", "attachments": 2}
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(ContractResponse.model_fields)
    assert body["category"] == "complaint.insult" and body["priority"] == "p1"
    assert body["extracted"]["nickname"] == "Arman_Test"
    assert body["extracted"]["has_evidence"] and body["needs_human"]
    with session_factory()() as db:
        row = db.query(TriageRun).one()
        assert row.category == "complaint.insult" and row.output["priority"] == "p1"


def test_http_rejects_labels_and_admin_messages(client):
    body = request().model_dump(mode="json")
    assert (
        client.post("/triage", json={**body, "verdict": "approved"}).status_code == 422
    )
    body["messages"].append({"role": "admin", "text": "ALREADY RESOLVED"})
    assert client.post("/triage", json=body).status_code == 422
    assert client.post("/triage", json={"text": "legacy"}).status_code == 422


def test_service_key_separate_from_crm(client, monkeypatch):
    monkeypatch.setenv("TRIAGE_API_KEY", "triage-key")
    settings.cache_clear()
    body = request().model_dump(mode="json")
    assert client.post("/triage", json=body).status_code == 401
    assert (
        client.post(
            "/triage", json=body, headers={"Authorization": "Bearer triage-key"}
        ).status_code
        == 200
    )


def test_export_strips_outcomes_and_admin_before_prompt(connected):
    raw = request().model_dump(mode="json")
    raw.update(
        verdict="GOLD_SECRET",
        punishment="GOLD_SECRET",
        violation="GOLD_SECRET",
        category="GOLD_SECRET",
        priority="GOLD_SECRET",
        status=2,
    )
    raw["messages"].append({"role": "admin", "text": "ADMIN_SECRET", "ts": "yesterday"})
    with model_reply() as call:
        output = run_triage(parse_export(raw))
    prompt = call.call_args.kwargs["json"]
    assert "GOLD_SECRET" not in json.dumps(prompt) and "ADMIN_SECRET" not in json.dumps(
        prompt
    )
    assert output.status == "ok" and output.needs_human
    assert output.telemetry["cost_usd"] > 0
    assert output.extracted.nickname == "Arman_Test"
    assert prompt["reasoning"] == {"effort": "none"}


@pytest.mark.parametrize(
    "code,value",
    [
        (
            "unknown_rule_reference",
            {
                "draft_reply": {
                    "lang": "ru",
                    "text": "Правило [99.9].",
                    "cited": ["99.9"],
                }
            },
        ),
        (
            "unknown_rule_reference",
            {"draft_reply": {"lang": "ru", "text": "Правило [99.9].", "cited": []}},
        ),
        (
            "unsupported_clause",
            {
                "draft_reply": {
                    "lang": "ru",
                    "text": "По пункту 99.8 и [2.1].",
                    "cited": ["2.1"],
                }
            },
        ),
        (
            "model_provided_url",
            {
                "draft_reply": {
                    "lang": "ru",
                    "text": "Смотрите https://fake.invalid и [2.1].",
                    "cited": ["2.1"],
                }
            },
        ),
        (
            "unsafe_draft_claim",
            {
                "draft_reply": {
                    "lang": "ru",
                    "text": "Игрок получит мут по [2.1].",
                    "cited": ["2.1"],
                }
            },
        ),
        ("wrong_category_kind", {"category": "report.question"}),
    ],
)
def test_guardrails_keep_billed_usage_and_route_human(client, connected, code, value):
    body = decision()
    body.update(value)
    with model_reply(body):
        response = client.post("/triage", json=request().model_dump(mode="json"))
    assert response.status_code == 502 and response.headers["x-triage-error"] == code
    assert (
        response.json()["needs_human"] and response.json()["draft_reply"]["cited"] == []
    )
    with session_factory()() as db:
        stored = db.query(TriageRun).one()
        assert (
            stored.output["telemetry"]["cost_usd"] > 0
            and stored.output["error"] == code
        )


def test_model_extraction_cannot_invent_evidence_or_nickname(connected):
    result = decision()
    result["extracted"].update(
        nickname="Invented_Fake",
        has_evidence=True,
        server="invented",
        rule_refs=["99.9"],
    )
    with model_reply(result):
        out = run_triage(request())
    assert out.extracted.nickname == "Arman_Test" and not out.extracted.has_evidence
    assert out.extracted.server is None and out.extracted.rule_refs == []


@pytest.mark.parametrize("kind", ["report", "complaint"])
def test_model_schema_limits_categories_to_request_kind(connected, kind):
    req = request(kind=kind)
    with model_reply(decision(req)) as call:
        out = run_triage(req)
    payload = call.call_args.kwargs["json"]
    allowed = payload["text"]["format"]["schema"]["properties"]["category"]["enum"]
    assert allowed and all(c.startswith(kind + ".") for c in allowed)
    assert all(c["code"] in allowed for c in json.loads(payload["input"])["taxonomy"])
    assert out.status == "ok"


@pytest.mark.parametrize(
    "text,cited",
    [
        ("Оскорбления запрещены.", ["2.1"]),
        ("Оскорбления запрещены [2.1].", []),
    ],
)
def test_known_citation_fields_are_reconciled_without_another_call(
    connected, text, cited
):
    body = decision()
    body["draft_reply"].update(text=text, cited=cited)
    with model_reply(body) as call:
        out = run_triage(request())
    assert out.status == "ok" and call.call_count == 1
    assert out.draft_reply.cited == ["2.1"]
    assert "[2.1]" in out.draft_reply.text
    assert out.citations[0]["clause"] == "2.1"


def test_payment_and_account_risk_cannot_auto_route(connected):
    req = request("Оплатил покупку, деньги списаны", kind="report")
    body = decision(req)
    body.update(category="report.question", priority="p3")
    with model_reply(body):
        out = run_triage(req)
    assert out.needs_human and out.priority == "p0"


def test_timeout_does_not_leak_exception_or_invent_cost(connected):
    with model_reply(exception=httpx.ReadTimeout("SECRET_TOKEN")):
        out = run_triage(request())
    assert out.error == "provider_timeout" and out.telemetry["cost_usd"] is None
    assert "SECRET_TOKEN" not in out.model_dump_json()


@pytest.mark.parametrize(
    "text,language",
    [
        ("Сәлем, маған көмек керек", "kk"),
        ("Сєлем, маґан кјмек керек", "kk"),
        ("Salom, menga yordam kerak", "uz"),
        ("Салом, менинг ҳисобим", "uz"),
        ("Здравствуйте", "ru"),
        ("Hello there", "en"),
        ("Hola, ayuda", "es"),
        ("Olá, ajuda", "pt"),
    ],
)
def test_language_hints_and_normalization(text, language):
    assert language_hint(text) == language
    assert normalize_kazakh("ўйин") == "ўйин"
    assert normalize_kazakh("ќґѕєјўї", "kk") == "қғңәөұү"


def test_retrieval_is_bounded_and_disambiguates_sections():
    sources = load_rules()
    got = retrieve(
        request("Читер стреляет, использует аимбот", rule_refs_raw="1.1"), sources
    )
    assert "gm30-5.2" in {r["id"] for r in got}
    assert len(got) <= settings().rag_top_k
    refs = {r["clause"] for r in sources}
    assert "GZ 1.1" in refs and "ЖБ 1.1.2" in refs


def test_evidence_is_metadata_not_a_claim():
    out = run_triage(request("Скриншоты есть, правило 2.1, сервер 03"))
    assert not out.extracted.has_evidence
    assert out.extracted.rule_refs == ["2.1"] and out.extracted.server == "03"


def test_duplicate_window_and_new_evidence_are_distinct(client):
    base = request(
        ticket_id="a", reporter_hash="same", created_at=datetime.now(timezone.utc)
    )
    seen = BatchDuplicates()
    assert not seen.check(base)
    assert seen.check(base.model_copy(update={"ticket_id": "b"}))
    assert not seen.check(base.model_copy(update={"images_count": 1}))
    assert not seen.check(
        base.model_copy(update={"created_at": base.created_at + timedelta(hours=2)})
    )
    first = client.post("/triage", json=base.model_dump(mode="json"))
    second = client.post(
        "/triage",
        json=base.model_copy(update={"ticket_id": "b"}).model_dump(mode="json"),
    )
    assert (
        not first.json()["is_spam_or_duplicate"]
        and second.json()["is_spam_or_duplicate"]
    )


def test_jsonl_and_http_same_engine_and_invalid_rows(tmp_path, client):
    a = request(ticket_id="one").model_dump(mode="json")
    raw = {
        **a,
        "messages": a["messages"] + [{"role": "admin", "text": "HIDDEN ANSWER"}],
        "verdict": "approved",
    }
    inp, out = tmp_path / "input.jsonl", tmp_path / "pred.jsonl"
    inp.write_text(
        json.dumps(raw)
        + "\nnot json\n"
        + json.dumps(
            request("Salom", kind="report", ticket_id="three").model_dump(mode="json")
        )
        + "\n"
    )
    assert predict(inp, out) == 1
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 3 and rows[1]["error"] == "invalid_input"
    assert {k: rows[0][k] for k in ContractResponse.model_fields} == client.post(
        "/triage", json=a
    ).json()


def test_batch_quota_stops_calls_and_keeps_rows(tmp_path, connected):
    inp, out = tmp_path / "input.jsonl", tmp_path / "pred.jsonl"
    inp.write_text(
        "\n".join(request(ticket_id=str(i)).model_dump_json() for i in range(3))
    )
    with model_reply(
        {
            "error": {
                "code": "rate_limit_exceeded",
                "type": "requests",
                "message": "requests per day RPD exceeded",
            }
        },
        status=429,
        headers={"Retry-After": "1728"},
    ) as call:
        assert predict(inp, out, rpm=0) == 1
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert call.call_count == 1 and len(rows) == 3
    assert (
        rows[0]["error"] == "provider_http_429"
        and rows[1]["error"] == "provider_quota_exhausted"
    )
    assert (
        rows[0]["telemetry"]["cost_usd"] is None
        and rows[1]["telemetry"]["cost_usd"] == 0
    )


def test_unlabelled_validation_never_fabricates_quality():
    req = request(ticket_id="a", lang="ru")
    pred = run_triage(req).model_dump()
    raw = {
        **req.model_dump(mode="json"),
        "verdict": "approved",
        "punishment": "a label from admin",
    }
    report = evaluate([raw], [pred], dataset_kind="organizer")
    assert (
        report["classification"]["accuracy"] is None
        and report["priority"]["macro_f1"] is None
    )
    assert (
        report["language_accuracy"] is None
        and report["label_coverage"]["category"] == 0
    )
    assert (
        report["runtime"]["ok"] == 1
        and report["draft_quality"]["scores"]["grounding"] is None
    )


def test_manual_labels_priority_and_category_evaluated_by_id():
    a, b = request(ticket_id="a"), request("Сәлем", kind="report", ticket_id="b")
    predictions = [run_triage(b).model_dump(), run_triage(a).model_dump()]
    gold = [
        {
            "ticket_id": "a",
            "category": "complaint.insult",
            "priority": "p2",
            "language": "ru",
            "needs_human": True,
            "label_source": "manual",
        },
        {
            "ticket_id": "b",
            "category": "report.offtopic",
            "priority": "p3",
            "language": "kk",
            "needs_human": True,
            "label_source": "manual",
        },
    ]
    report = evaluate(gold, predictions)
    assert (
        report["classification"]["accuracy"] == 1
        and report["priority"]["macro_f1"] == 1
    )
    assert report["language_accuracy"] == 1 and report["needs_human"]["recall"] == 1


def test_metrics_and_unlabelled_upload_admin_only(admin):
    req = request(ticket_id="one")
    out = run_triage(req)
    record_run(req, out, source="batch", request_key="same")
    record_run(
        req,
        out.model_copy(update={"telemetry": {**out.telemetry, "attempt_id": "second"}}),
        source="batch",
        request_key="same",
    )
    response = admin.get("/api/metrics?provider=offline")
    assert (
        response.json()["summary"]["requests"] == 1
        and response.json()["summary"]["attempts"] == 2
    )
    assert response.json()["priorities"]["p2"] == 1
    upload = admin.post(
        "/api/evaluations",
        json={
            "name": "Unlabelled",
            "dataset_kind": "organizer",
            "gold": [req.model_dump(mode="json")],
            "predictions": [out.model_dump(mode="json")],
        },
    )
    assert (
        upload.status_code == 200
        and upload.json()["report"]["classification"]["accuracy"] is None
    )


def test_worker_daily_quota_fails_immediately(admin, complaint):
    from app.worker import run_once

    with patch(
        "app.worker.analyze",
        side_effect=TriageFailure(
            "provider_http_429",
            provider_error={"limit_scope": "day"},
            retry_after_seconds=1728,
        ),
    ):
        run_once()
    with session_factory()() as db:
        job = db.query(Job).filter_by(kind="analyze").one()
        assert (
            job.state == "failed"
            and job.attempts == 1
            and job.error == "provider_daily_quota_exhausted"
        )


def test_worker_respects_server_retry_after(admin, complaint):
    from app.worker import run_once

    before = datetime.now(timezone.utc)
    with patch(
        "app.worker.analyze",
        side_effect=TriageFailure("provider_http_429", retry_after_seconds=1728),
    ):
        run_once()
    with session_factory()() as db:
        job = db.query(Job).filter_by(kind="analyze").one()
        assert job.state == "pending"
        assert (
            job.available_at.replace(tzinfo=timezone.utc) - before
        ).total_seconds() >= 1728


def test_worker_invalid_output_is_not_retried(admin, complaint):
    from app.models import Ticket
    from app.worker import run_once

    with patch(
        "app.worker.analyze", side_effect=TriageFailure("invalid_model_response")
    ) as call:
        assert run_once()
        assert not run_once()
    assert call.call_count == 1
    with session_factory()() as db:
        job = db.query(Job).filter_by(kind="analyze").one()
        assert job.state == "failed" and job.attempts == 1
        assert db.get(Ticket, complaint["id"]).status == "review"


def test_known_and_unknown_token_prices(monkeypatch):
    assert (
        token_cost({"input_tokens": 1000, "output_tokens": 100}, "gpt-6-luna")[0]
        == 0.00015
    )
    assert (
        token_cost({"input_tokens": 1000, "output_tokens": 100}, "unknown")[0] is None
    )
    assert token_cost(None, "gpt-6-luna")[0] is None


def test_handout_missing_never_sends_uncontextualized_prompt(
    connected, monkeypatch, tmp_path
):
    monkeypatch.setenv("HANDOUT_DIR", str(tmp_path / "missing"))
    settings.cache_clear()
    with model_reply() as call:
        out = run_triage(request())
    assert not call.called and out.error == "handout_not_loaded" and out.needs_human
    assert out.telemetry["cost_usd"] == 0


def test_batch_long_token_cooldown_is_not_waited(tmp_path, connected):
    inp, out = tmp_path / "input.jsonl", tmp_path / "pred.jsonl"
    inp.write_text(
        "\n".join(request(ticket_id=str(i)).model_dump_json() for i in range(3))
    )
    with model_reply(
        {
            "error": {
                "code": "rate_limit_exceeded",
                "type": "tokens",
                "message": "Token rate limit",
            }
        },
        status=429,
        headers={"Retry-After": "25000"},
    ) as call:
        assert predict(inp, out, rpm=0) == 1
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert call.call_count == 1 and len(rows) == 3
    assert (
        rows[1]["error"] == "provider_cooldown"
        and not rows[1]["telemetry"]["called_provider"]
    )


def test_password_reset_revokes_sessions(admin, monkeypatch):
    from app.cli import main
    from app.models import AuthSession

    with session_factory()() as db:
        assert db.query(AuthSession).count() == 1
    monkeypatch.setenv("COPILOT_STAFF_PASSWORD", "Replacement-Password-2026!")
    monkeypatch.setattr("sys.argv", ["copilot", "reset-password", "--login", "admin"])
    main()
    assert admin.get("/api/auth/me").status_code == 401
    response = admin.post(
        "/api/auth/login",
        json={"login": "admin", "password": "Replacement-Password-2026!"},
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    "text,server_lang",
    [
        ("Сәлем! Ойыншыны қорлауға бола ма?", "kk"),
        ("Сєлем, ойыншыны балаґаттауґа бола ма?", "kk"),
        ("Salom, boshqa o'yinchini haqorat qilish mumkinmi?", "uz"),
        ("Салом! Бошқа ўйинчини ҳақорат қилиш мумкинми?", "uz"),
    ],
)
def test_multilingual_rag_retrieves_russian_insult_rule(text, server_lang):
    got = retrieve(request(text, kind="report", server_lang=server_lang), load_rules())
    assert "gm30-2.1" in {s["id"] for s in got}
