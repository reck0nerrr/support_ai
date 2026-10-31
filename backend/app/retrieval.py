"""Local BM25 with multilingual query expansion; no API or vector database required."""

from collections import Counter
from functools import lru_cache
import json
import math
import re

from .config import settings
from .languages import normalize_kazakh
from .routing import topics

EXPANSION = {
    "insult": "оскорбление родственников личность расизм национальность чат",
    "cheat": "читы стороннее программное обеспечение запрещенные программы",
    "dm": "убийство урон причина DM DB зеленая зона GZ роль RP",
    "scam": "обман мошенничество имущество сделка деньги транспорт обмен",
    "rmt_ads": "продажа аккаунта реальные деньги реклама сторонний ресурс",
    "admin": "администратор жалоба наказание обжалование апелляция",
    "account": "аккаунт сохранность пароль взлом имущество восстановление",
    "payment": "покупка донат платеж возврат деньги",
    "help": "баг помощь администратор телепорт текстуры техническая проблема",
    "question": "правила RP роль",
}
STOP = {
    "это",
    "как",
    "меня",
    "мне",
    "что",
    "для",
    "или",
    "при",
    "его",
    "она",
    "они",
    "есть",
    "прошу",
    "игрок",
    "игрока",
    "правил",
    "правило",
}


def tokens(text):
    return [
        w[:6] if len(w) > 6 else w
        for w in re.findall(r"[\w]+", text.lower().replace("ё", "е"))
        if len(w) > 1 and w not in STOP
    ]


@lru_cache(maxsize=4)
def index(serialized):
    sources = json.loads(serialized)
    docs = [Counter(tokens(s["title"] + " " + s["text"])) for s in sources]
    df = Counter(term for d in docs for term in d)
    lengths = [sum(d.values()) for d in docs]
    return sources, docs, df, lengths, sum(lengths) / max(len(lengths), 1)


def retrieve(request, sources):
    sources, docs, df, lengths, avg = index(
        json.dumps(sources, ensure_ascii=False, sort_keys=True)
    )
    text = normalize_kazakh(request.text, request.server_lang)
    query = text + " " + " ".join(EXPANSION[t] for t in topics(text))
    terms = Counter(tokens(query))
    raw_refs = set(
        re.findall(r"\d+\.\d+(?:\.\d+)*", request.rule_refs_raw + " " + text)
    )
    ranked = []
    for i, (source, doc) in enumerate(zip(sources, docs)):
        score = 0.0
        for term, weight in terms.items():
            tf = doc.get(term, 0)
            if tf:
                idf = math.log(1 + (len(docs) - df[term] + 0.5) / (df[term] + 0.5))
                score += (
                    idf
                    * tf
                    * 2.2
                    / (tf + 1.2 * (0.25 + 0.75 * lengths[i] / max(avg, 1)))
                    * min(weight, 2)
                )
        # Player refs are a weak retrieval hint, never a verified rule selection.
        if source.get("raw_ref", source["clause"]) in raw_refs:
            score += 1.5 if source.get("section") == 30 else 0.25
        if request.kind == "complaint" and source.get("section") == 31:
            score += 0.3
        ranked.append((score, i))
    selected, chars = [], 0
    for score, i in sorted(ranked, reverse=True):
        if score <= 0 or len(selected) >= settings().rag_top_k:
            break
        source = sources[i]
        size = len(source["text"]) + len(source["title"])
        if chars + size > settings().rag_max_chars:
            continue
        selected.append(source)
        chars += size
    return selected
