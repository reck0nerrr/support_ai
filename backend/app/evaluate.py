"""Evaluate predictions against separate gold labels; write JSON + Markdown and optional CRM snapshot."""

import argparse
import json
from pathlib import Path
import sys
from .evaluation import evaluate, markdown_report, read_jsonl


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", required=True)
    parser.add_argument("--pred", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown")
    parser.add_argument("--reviews")
    parser.add_argument("--name", default="Support Copilot · evaluation")
    parser.add_argument(
        "--dataset-kind",
        choices=["synthetic", "organizer", "real-reviewed", "unknown"],
        default="unknown",
    )
    parser.add_argument("--persist", action="store_true")
    args = parser.parse_args()
    try:
        report = evaluate(
            read_jsonl(args.gold),
            read_jsonl(args.pred),
            read_jsonl(args.reviews) if args.reviews else None,
            name=args.name,
            dataset_kind=args.dataset_kind,
        )
        Path(args.out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if args.markdown:
            Path(args.markdown).write_text(markdown_report(report), encoding="utf-8")
        if args.persist:
            from .db import session_factory
            from .models import EvaluationRun

            with session_factory()() as db, db.begin():
                db.add(EvaluationRun(name=args.name, report=report))
        print(
            f"Evaluated {report['counts']['gold']} requests; category labels={report['label_coverage']['category']}, priority labels={report['label_coverage']['priority']}; report saved.",
            file=sys.stderr,
        )
    except (OSError, ValueError):
        print(
            "Evaluation failed: check JSONL schemas, unique ids, labels, reviews and output paths.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
