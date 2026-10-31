"""Private annotation samples and draft template suggestions. No inference calls."""

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import random
import re

from .contract import parse_export


def records(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8-sig") as stream:
        for line in stream:
            yield json.loads(line)


def annotation_sample(path, count=120, seed=20261027):
    groups = defaultdict(list)
    for row in records(path):
        groups[(row.get("lang", "und"), row["kind"])].append(row)
    rng = random.Random(seed)
    for group in groups.values():
        rng.shuffle(group)
    selected = []
    while len(selected) < count and any(groups.values()):
        for group in groups.values():
            if group and len(selected) < count:
                raw = group.pop()
                request = parse_export(raw)
                selected.append(
                    {
                        **request.model_dump(mode="json"),
                        "category": None,
                        "priority": None,
                        "language": None,
                        "needs_human": None,
                        "label_source": "manual-pending",
                    }
                )
    return selected


def template_suggestions(path, minimum=5):
    groups = defaultdict(Counter)
    questions = {}
    for row in records(path):
        if row.get("kind") != "report":
            continue
        question = " ".join(
            m.get("text", "")
            for m in row.get("messages", [])
            if m.get("role") == "player"
        ).strip()
        answers = [
            m.get("text", "").strip()
            for m in row.get("messages", [])
            if m.get("role") == "admin"
        ]
        if len(question) < 10 or len(question) > 250 or not answers:
            continue
        key = re.sub(r"\W+", " ", question.casefold()).strip()
        groups[key].update(a for a in answers if a)
        questions.setdefault(key, question)
    result = []
    for key, answers in sorted(
        groups.items(), key=lambda pair: sum(pair[1].values()), reverse=True
    ):
        n = sum(answers.values())
        if n < minimum:
            continue
        result.append(
            {
                "cluster_id": hashlib.sha256(key.encode()).hexdigest()[:16],
                "question": questions[key],
                "occurrences": n,
                "candidate_answers": [
                    {"text": text, "count": count}
                    for text, count in answers.most_common(3)
                ],
                "review_required": True,
                "note": "Historical replies can be unsafe or outdated. Suggestions are never added to the live knowledge base automatically.",
            }
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["sample", "templates"])
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--count", type=int, default=120)
    args = parser.parse_args()
    rows = (
        annotation_sample(args.input, args.count)
        if args.mode == "sample"
        else template_suggestions(args.input)
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Saved {len(rows)} private review records; no LLM calls.")


if __name__ == "__main__":
    main()
