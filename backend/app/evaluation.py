"""Deterministic metrics. No LLM-as-judge scores or invented ground truth."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .knowledge import bundled_rules


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    lo, hi = math.floor(position), math.ceil(position)
    return round(values[lo] + (values[hi] - values[lo]) * (position - lo), 2)


def runtime_summary(predictions, *, attempts=None):
    attempts = attempts if attempts is not None else predictions
    n = len(predictions)
    tokens = [p.get("telemetry", {}).get("usage") for p in attempts]
    costs = [p.get("telemetry", {}).get("cost_usd") for p in attempts]
    known = [v for v in costs if isinstance(v, (float, int))]
    latencies = [
        p["telemetry"]["latency_ms"]
        for p in attempts
        if isinstance(p.get("telemetry", {}).get("latency_ms"), (int, float))
    ]
    llm_times = [
        p["telemetry"]["llm_latency_ms"]
        for p in attempts
        if isinstance(p.get("telemetry", {}).get("llm_latency_ms"), (int, float))
    ]
    successes = [p for p in attempts if p.get("status") == "ok"]
    success_times = [
        p["telemetry"]["latency_ms"]
        for p in successes
        if isinstance(p.get("telemetry", {}).get("latency_ms"), (int, float))
    ]
    success_costs = [
        p["telemetry"]["cost_usd"]
        for p in successes
        if isinstance(p.get("telemetry", {}).get("cost_usd"), (int, float))
    ]
    return {
        "requests": n,
        "attempts": len(attempts),
        "ok": sum(p.get("status") == "ok" for p in predictions),
        "errors": sum(p.get("status") != "ok" for p in predictions),
        "needs_human_count": sum(p.get("needs_human") is True for p in predictions),
        "needs_human_rate": sum(p.get("needs_human") is True for p in predictions) / n
        if n
        else None,
        "latency_p50_ms": percentile(latencies, 0.5),
        "latency_p95_ms": percentile(latencies, 0.95),
        "llm_p50_ms": percentile(llm_times, 0.5),
        "llm_p95_ms": percentile(llm_times, 0.95),
        "latency_samples": len(latencies),
        "successful_latency_p50_ms": percentile(success_times, 0.5),
        "successful_latency_p95_ms": percentile(success_times, 0.95),
        "priced_successes": len(success_costs),
        "cost_per_priced_success_usd": round(
            sum(success_costs) / len(success_costs), 10
        )
        if success_costs
        else None,
        "batch_pacing_total_ms": sum(
            p.get("telemetry", {}).get("batch_pacing_ms", 0) for p in attempts
        ),
        "known_cost_usd": round(sum(known), 10),
        "priced_attempts": len(known),
        "cost_coverage": len(known) / len(attempts) if attempts else None,
        "cost_per_request_usd": round(sum(known) / n, 10)
        if n and len(known) == len(attempts)
        else None,
        "input_tokens": sum(t.get("input_tokens", 0) for t in tokens if t),
        "output_tokens": sum(t.get("output_tokens", 0) for t in tokens if t),
        "usage_samples": sum(t is not None for t in tokens),
        "providers": dict(
            Counter(p.get("telemetry", {}).get("provider", "unknown") for p in attempts)
        ),
        "models": dict(
            Counter(p.get("telemetry", {}).get("model", "unknown") for p in attempts)
        ),
        "prompt_versions": sorted(
            {p.get("telemetry", {}).get("prompt_version", "unknown") for p in attempts}
        ),
        "corpus_versions": sorted(
            {p.get("telemetry", {}).get("corpus_version", "unknown") for p in attempts}
        ),
        "errors_by_code": dict(
            Counter(
                p.get("error", "unknown") for p in attempts if p.get("status") != "ok"
            )
        ),
    }


def classification_metrics(pairs):
    if not pairs:
        return {
            "n": 0,
            "accuracy": None,
            "macro_f1": None,
            "per_class": {},
            "confusion": {},
        }
    labels = sorted(
        {g["category"] for g, _ in pairs}
        | {
            p["category"]
            for _, p in pairs
            if p and p.get("status") == "ok" and p.get("category")
        }
    )
    confusion = {}
    for gold, pred in pairs:
        actual = gold["category"]
        guessed = (
            pred["category"]
            if pred and pred.get("status") == "ok" and pred.get("category")
            else "__error__"
        )
        confusion.setdefault(actual, {})[guessed] = (
            confusion.get(actual, {}).get(guessed, 0) + 1
        )
    per_class = {}
    for label in labels:
        tp = confusion.get(label, {}).get(label, 0)
        fp = sum(v.get(label, 0) for k, v in confusion.items() if k != label)
        fn = sum(confusion.get(label, {}).values()) - tp
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0,
            "support": tp + fn,
        }
    correct = sum(v.get(k, 0) for k, v in confusion.items())
    return {
        "n": len(pairs),
        "accuracy": correct / len(pairs),
        "macro_f1": sum(v["f1"] for v in per_class.values()) / len(labels),
        "per_class": per_class,
        "confusion": confusion,
    }


def key(value):
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError("Each row needs a non-null string or integer id")
    return json.dumps(value, ensure_ascii=False)


def read_jsonl(path):
    result = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"Blank JSONL row at line {line_number}")
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON at line {line_number}") from None
            if not isinstance(value, dict):
                raise ValueError(f"Expected object at line {line_number}")
            result.append(value)
    return result


def index_rows(rows):
    result = {}
    for row in rows:
        identity = key(row.get("id"))
        if identity in result:
            raise ValueError("Duplicate id in dataset")
        result[identity] = row
    return result


def normalize_prediction(row):
    from .contract import Prediction
    from .schemas import TriageResponse

    if "draft_reply" not in row:
        TriageResponse.model_validate(row)
        return row
    p = Prediction.model_validate(row)
    rules = {r["clause"]: r for r in bundled_rules() if r["clause"]}
    supplied = {c.get("clause"): c for c in p.citations}
    citations = []
    for ref in p.draft_reply.cited:
        source = supplied.get(ref) or rules.get(ref)
        citations.append(
            {k: source.get(k, "") for k in ("id", "clause", "title", "url", "version")}
            if source
            else {
                "id": "unknown:" + ref,
                "clause": ref,
                "title": "",
                "url": "",
                "version": "",
            }
        )
    return {
        "id": p.ticket_id,
        "status": p.status,
        "category": p.category,
        "priority": p.priority,
        "language": p.lang,
        "draft": p.draft_reply.text,
        "needs_human": p.needs_human,
        "human_reasons": p.reasons,
        "intent": p.intent,
        "telemetry": p.telemetry,
        "error": p.error,
        "citations": citations,
        "is_spam_or_duplicate": p.is_spam_or_duplicate,
    }


def normalize_gold(row):
    from .contract import CATEGORIES
    from .schemas import Category
    from typing import get_args

    result = {
        "id": row.get("id", row.get("ticket_id")),
        "category": row.get("category"),
        "priority": row.get("priority"),
        "language": row.get("language"),
        "language_hint": row.get("lang"),
        "needs_human": row.get("needs_human"),
        "label_source": row.get("label_source", "unspecified"),
    }
    if result["category"] is not None and result["category"] not in set(
        CATEGORIES
    ) | set(get_args(Category)):
        raise ValueError("Unsupported gold category")
    if result["priority"] is not None and result["priority"] not in {
        "p0",
        "p1",
        "p2",
        "p3",
    }:
        raise ValueError("Unsupported gold priority")
    if result["language"] is not None and result["language"] not in {
        "ru",
        "kk",
        "uz",
        "en",
        "es",
        "pt",
    }:
        raise ValueError("Unsupported gold language")
    if result["needs_human"] is not None and type(result["needs_human"]) is not bool:
        raise ValueError("needs_human must be boolean or null")
    if result["label_source"] == "manual-pending" and any(
        result[k] is not None
        for k in ("category", "priority", "language", "needs_human")
    ):
        raise ValueError("Mark completed human labels as label_source=manual")
    if "rule_ids" in row:
        if not isinstance(row["rule_ids"], list) or any(
            not isinstance(x, str) for x in row["rule_ids"]
        ):
            raise ValueError("rule_ids must be strings")
        result["rule_ids"] = row["rule_ids"]
    return result


def evaluate(
    gold, predictions, reviews=None, *, name="Evaluation", dataset_kind="unknown"
):
    raw_gold, raw_predictions = gold, predictions
    gold = [normalize_gold(g) for g in gold]
    predictions = [normalize_prediction(p) for p in predictions]
    gold_by_id, pred_by_id = index_rows(gold), index_rows(predictions)
    if not gold:
        raise ValueError("Gold dataset is empty")
    pairs = [(g, pred_by_id.get(identity)) for identity, g in gold_by_id.items()]
    category_pairs = [(g, p) for g, p in pairs if g["category"] is not None]
    priority_pairs = [
        (
            {**g, "category": g["priority"]},
            {**p, "category": p.get("priority")} if p else None,
        )
        for g, p in pairs
        if g["priority"] is not None
    ]
    language_pairs = [(g, p) for g, p in pairs if g["language"] is not None]
    correct_language = sum(
        p is not None and p.get("status") == "ok" and g["language"] == p["language"]
        for g, p in language_pairs
    )
    nh_pairs = [
        (g["needs_human"], p["needs_human"] if p and p.get("status") == "ok" else True)
        for g, p in pairs
        if g["needs_human"] is not None
    ]
    tp = sum(a and b for a, b in nh_pairs)
    fp = sum(not a and b for a, b in nh_pairs)
    fn = sum(a and not b for a, b in nh_pairs)
    rules = {r["id"]: r for r in bundled_rules()}
    citations = [c for _, p in pairs if p for c in p["citations"]]
    valid = sum(
        c["id"] in rules
        and all(c[k] == rules[c["id"]][k] for k in ("url", "clause", "version"))
        for c in citations
    )
    citation_pairs = [
        (
            set(g["rule_ids"]),
            {c["id"] for c in p["citations"]} if p and p["status"] == "ok" else set(),
        )
        for g, p in pairs
        if "rule_ids" in g
    ]
    ctp = sum(len(a & b) for a, b in citation_pairs)
    predicted_c, expected_c = (
        sum(len(b) for a, b in citation_pairs),
        sum(len(a) for a, b in citation_pairs),
    )
    reviews = reviews or []
    review_index = index_rows(
        [{**r, "id": r.get("id", r.get("ticket_id"))} for r in reviews]
    )
    score_names = ("correctness", "usefulness", "language", "grounding")
    for identity, review in review_index.items():
        if identity not in gold_by_id or identity not in pred_by_id:
            raise ValueError("Review has no gold/prediction pair")
        if any(
            type(review.get(k)) is not int or not 1 <= review[k] <= 5
            for k in score_names
        ):
            raise ValueError("Reviews require four integer scores from 1 to 5")
        if type(review.get("citations_supported")) is not bool:
            raise ValueError("citations_supported must be boolean")
    runtime = runtime_summary(predictions)

    def group_language(g, p):
        return g["language"] or (
            g["language_hint"]
            if g["language_hint"] in {"ru", "kk", "uz", "en", "es", "pt"}
            else "und"
        )

    by_language = {}
    for lang in sorted({group_language(g, p) for g, p in pairs}):
        group = [(g, p) for g, p in pairs if group_language(g, p) == lang]
        labelled = [(g, p) for g, p in group if g["category"] is not None]
        labelled_lang = [(g, p) for g, p in group if g["language"] is not None]
        by_language[lang] = {
            **classification_metrics(labelled),
            "n": len(group),
            "labelled_n": len(labelled),
            "language_accuracy": sum(
                p is not None and p["status"] == "ok" and p["language"] == g["language"]
                for g, p in labelled_lang
            )
            / len(labelled_lang)
            if labelled_lang
            else None,
            "runtime": runtime_summary([p for _, p in group if p]),
        }
    selected, examples = set(), []
    ordered = sorted(
        pairs, key=lambda pair: not (pair[1] and pair[1]["status"] == "ok")
    )
    for lang in by_language:
        for g, p in ordered:
            if group_language(g, p) == lang and p:
                selected.add(key(g["id"]))
                examples.append(
                    {
                        "id": g["id"],
                        "expected": {
                            **g,
                            "language": g["language"] or group_language(g, p),
                        },
                        "prediction": p,
                    }
                )
                break
    for g, p in sorted(
        pairs, key=lambda pair: bool(pair[1] and pair[1]["status"] == "ok")
    ):
        if len(examples) >= 9:
            break
        if key(g["id"]) not in selected:
            examples.append(
                {
                    "id": g["id"],
                    "expected": {
                        **g,
                        "language": g["language"] or group_language(g, p),
                    },
                    "prediction": p,
                }
            )
    return {
        "schema_version": "2.0",
        "name": name,
        "dataset_kind": dataset_kind,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(
            json.dumps(raw_gold, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "predictions_sha256": hashlib.sha256(
            json.dumps(raw_predictions, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest(),
        "counts": {
            "gold": len(gold),
            "predictions": len(predictions),
            "missing": len(gold_by_id.keys() - pred_by_id.keys()),
            "unexpected": len(pred_by_id.keys() - gold_by_id.keys()),
            "reviewed": len(reviews),
        },
        "label_coverage": {
            "category": len(category_pairs),
            "priority": len(priority_pairs),
            "language": len(language_pairs),
            "needs_human": len(nh_pairs),
            "sources": dict(
                Counter(
                    g["label_source"] for g in gold if g["category"] or g["priority"]
                )
            ),
        },
        "classification": classification_metrics(category_pairs),
        "priority": classification_metrics(priority_pairs),
        "language_accuracy": correct_language / len(language_pairs)
        if language_pairs
        else None,
        "needs_human": {
            "n": len(nh_pairs),
            "accuracy": sum(a == b for a, b in nh_pairs) / len(nh_pairs)
            if nh_pairs
            else None,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "false_negative": fn,
            "false_positive": fp,
            "error_policy": "missing/error predictions route to human",
        },
        "citations": {
            "count": len(citations),
            "valid_count": valid,
            "validity_rate": valid / len(citations) if citations else None,
            "gold_labeled_requests": len(citation_pairs),
            "precision": ctp / predicted_c if predicted_c else None,
            "recall": ctp / expected_c if expected_c else None,
            "guardrail_rejections": sum(
                p.get("error")
                in {
                    "unknown_rule_reference",
                    "unknown_draft_reference",
                    "unsupported_clause",
                    "model_provided_url",
                    "missing_draft_reference",
                    "unsafe_draft_claim",
                }
                for p in predictions
            ),
            "entailment_reviewed": len(reviews),
            "human_supported_rate": sum(r["citations_supported"] for r in reviews)
            / len(reviews)
            if reviews
            else None,
        },
        "draft_quality": {
            "reviewed": len(reviews),
            "scale": "1-5, manually reviewed",
            "scores": {
                s: sum(r[s] for r in reviews) / len(reviews) if reviews else None
                for s in score_names
            },
        },
        "runtime": runtime,
        "by_language": by_language,
        "examples": examples,
        "targets": {
            "cost_limit_usd": 0.002,
            "latency_p95_limit_ms": 5000,
            "cost_pass": runtime["cost_per_request_usd"] <= 0.002
            if runtime["cost_per_request_usd"] is not None
            else None,
            "latency_pass": runtime["successful_latency_p95_ms"] <= 5000
            if runtime["successful_latency_p95_ms"] is not None
            else None,
        },
        "limitations": [
            "Category/priority labels absent in the official validation export: unlabelled rows never enter accuracy/F1.",
            "Export lang is a heuristic hint, not a gold language label. Native-speaker review is still required.",
            "Admin replies, verdicts, punishments and violations are excluded from inference inputs.",
            "Existing rule IDs do not prove relevance; semantic grounding and draft quality require manual review.",
            "Offline baseline results do not measure LLM draft quality. Synthetic checks are not organizer benchmarks.",
            "Latency excludes queue/pacing; errors and successful calls are reported separately. Cost is a token estimate, not an invoice.",
            "Reports containing organizer examples are private and must not be published.",
        ],
    }


def markdown_report(report):
    def percent(v):
        return f"{v * 100:.1f}%" if v is not None else "нет данных"

    r, c = report["runtime"], report["classification"]
    cost = (
        f"${r['cost_per_request_usd']:.8f}"
        if r["cost_per_request_usd"] is not None
        else "неизвестна: нужен тариф и usage для каждого вызова"
    )
    rows = [
        f"# {report['name']}",
        "",
        f"Тип выборки: **{report['dataset_kind']}**. Дата: {report['created_at']}",
        f"Провайдеры: {r['providers']}; модели: {r['models']}",
        "",
        "| Метрика | Значение |",
        "| --- | ---: |",
        f"| Обращений в эталоне | {report['counts']['gold']} |",
        f"| Ошибок выполнения | {r['errors']} |",
        f"| Accuracy | {percent(c['accuracy'])} |",
        f"| Macro-F1 категории | {percent(c['macro_f1'])} |",
        f"| Macro-F1 приоритета | {percent(report.get('priority', {}).get('macro_f1'))} |",
        f"| Размечено категорий / приоритетов | {report.get('label_coverage', {}).get('category', 0)} / {report.get('label_coverage', {}).get('priority', 0)} |",
        f"| Язык ответа | {percent(report['language_accuracy'])} |",
        f"| Доля needs_human | {percent(r['needs_human_rate'])} |",
        f"| Recall needs_human | {percent(report['needs_human']['recall'])} |",
        f"| Валидность возвращённых ссылок | {percent(report['citations']['validity_rate'])} |",
        f"| Отклонено ответов проверкой ссылок | {report['citations']['guardrail_rejections']} |",
        f"| p50 / p95 обработки, мс | {r['latency_p50_ms']} / {r['latency_p95_ms']} |",
        f"| Стоимость на обращение | {cost} |",
        f"| Покрытие расчётом стоимости | {percent(r['cost_coverage'])} |",
        f"| Успешный вызов с известным тарифом, USD | {r['cost_per_priced_success_usd']} (n={r['priced_successes']}) |",
        f"| p50 / p95 успешных вызовов, мс | {r['successful_latency_p50_ms']} / {r['successful_latency_p95_ms']} |",
        f"| Ожидание темпа JSONL, мс суммарно | {r['batch_pacing_total_ms']} |",
        "",
        "Оценка качества черновиков: "
        + (
            str(report["draft_quality"]["scores"])
            if report["counts"]["reviewed"]
            else "ожидает ручной проверки; оценка не выдумывается."
        ),
        "",
        "## По языкам",
        "",
        "| Язык | N | Accuracy | Macro-F1 | Язык ответа |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for language, group in report["by_language"].items():
        rows.append(
            f"| {language} | {group['n']} | {percent(group['accuracy'])} | {percent(group['macro_f1'])} | {percent(group['language_accuracy'])} |"
        )
    rows += ["", "## Примеры черновиков", ""]
    for example in report["examples"]:
        p = example["prediction"]
        rows += [
            f"### {example['id']}",
            "",
            f"Эталон: {example['expected']['category']} · {example['expected']['language']}",
            "",
        ]
        if p:
            rows += [
                f"Результат: {p['category']}; needs_human={p['needs_human']}; status={p['status']}",
                "",
                p["draft"],
                "",
            ]
        else:
            rows += ["Предсказание отсутствует.", ""]
    rows += ["## Ограничения", ""] + [f"- {v}" for v in report["limitations"]]
    return "\n".join(rows) + "\n"
