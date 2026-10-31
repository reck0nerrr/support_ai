"""Read organizer data locally. Never execute or publish contents of the archive."""

import argparse
import hashlib
import json
from pathlib import Path
import tarfile

from .config import settings

FILES = (
    "README.md",
    "taxonomy.json",
    "rules.json",
    "tickets_valid.jsonl",
    "tickets_train.jsonl.gz",
)
PREFIXES = {
    30: "",
    31: "ЖБ",
    32: "GZ",
    33: "ЛИД",
    34: "ГОС",
    35: "ДЕП",
    36: "СЕМ",
    40: "ОПГ",
    41: "БИЗ",
    42: "ФУР",
}


def directory():
    return Path(settings().handout_dir).expanduser()


def load_rules():
    path = directory() / "rules.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    version = "handout-" + hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    result = []
    for section in data["rules"]:
        sid = section["id"]
        for point in section.get("points", []):
            raw = str(point["ref"])
            prefix = PREFIXES.get(sid, str(sid))
            ref = f"{prefix} {raw}".strip()
            result.append(
                {
                    "id": f"gm{sid}-{raw}",
                    "clause": ref,
                    "raw_ref": raw,
                    "title": section["category"],
                    "section": sid,
                    "text": point["text"],
                    "version": version,
                    "url": "",
                }
            )
        if not section.get("points") and section.get("text"):
            result.append(
                {
                    "id": f"gm{sid}-kb",
                    "clause": "",
                    "raw_ref": "",
                    "title": section["category"],
                    "section": sid,
                    "text": section["text"],
                    "version": version,
                    "url": "",
                }
            )
    return result


def taxonomy():
    return json.loads((directory() / "taxonomy.json").read_text(encoding="utf-8"))


def import_archive(archive, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if target.parent.name == "private":
        target.parent.chmod(0o700)
    target.mkdir(parents=True, exist_ok=True, mode=0o755)
    target.chmod(0o755)
    manifest = {}
    with tarfile.open(archive, "r:gz") as tar:
        members = {m.name: m for m in tar.getmembers()}
        for name in FILES:
            member = members.get(f"handout/{name}")
            if member is None or not member.isfile() or member.size > 100_000_000:
                raise ValueError("Invalid or missing handout member")
        for name in FILES:
            payload = tar.extractfile(members[f"handout/{name}"]).read()
            path = target / name
            path.write_bytes(payload)
            path.chmod(0o644)
            manifest[name] = hashlib.sha256(payload).hexdigest()
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Import the organizer handout into an ignored private directory"
    )
    parser.add_argument("--archive", required=True)
    parser.add_argument("--out", default=str(directory()))
    args = parser.parse_args()
    import_archive(args.archive, args.out)
    print("Imported handout locally. Do not commit or publish this directory.")


if __name__ == "__main__":
    main()
