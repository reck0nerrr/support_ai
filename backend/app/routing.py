"""Conservative extraction and routing gates; player claims are never verified facts."""

import re
from .contract import Extracted
from .languages import normalize_kazakh

TOPICS = {
    "insult": r"оскорб|матер|родн|расис|наци[зс]|балағат|қорла|haqorat|ҳақорат|хақорат|so['’ʻ]k|сўк|сөк|oskorb|semyu|токсич",
    "cheat": r"\bчит\w*|читер|aimbot|аимбот|телепортир|сквозь стен|cheater|chit|чит қолдан",
    "dm": r"\bdm\b|\bd[bm]\b|\bдм\b|\bдб\b|уби[лт]|урон|стреля|өлтір|o'ldir|ўлдир|bez prich|отстрел",
    "scam": r"обман|мошенн|кину[лт]|не отдал|не вернул|aldadi|алда|firib|фириб|вымога|scam|aldab",
    "rmt_ads": r"rmt|рмт|за реал|реальн.*день|прода[юе].*аккаунт|реклам|sotaman|аккаунт.*сат|продажа аккаунт",
    "admin": r"админ|администратор|апелляц|разбан|обжал|не соглас.*(?:бан|мут|наказ)|appeal|unban",
    "account": r"взлом|аккаунт|парол|доступ.*потер|пропал.*(?:машин|имущ)|hacked|password|akkaunt|аккаунт|бұз|буз|parol|kir[ao]lma",
    "payment": r"донат|оплат|плат[её]ж|списа[лн]|возврат.*(?:покуп|денег)|payment|refund|charged|to['’ʻ]lov|тўлов|төлем|сатып ал",
    "help": r"застря|текстур|телепорт|баг|вылет|краш|қатып|bug|stuck|qotib|помогите выбра|лаг",
    "question": r"как |где |зачем |что такое|можно ли|қалай|қайда|неге|деген не|бола ма|qanday|qayer|nima|mumkin|қандай|нима|мумкин|қаер|how |where |what |como |dónde ",
}
PATTERNS = {k: re.compile(v, re.I) for k, v in TOPICS.items()}
URGENT = re.compile(
    r"взлом|hacked|бұз|вход.*потер|потер.*доступ|украл.*аккаунт|массов.*баг|угроз.*(?:жизн|адрес|убь)|убью.*(?:реал|жизн)|akkaunt.*buz|аккаунт.*буз",
    re.I,
)
PERSONAL = re.compile(
    r"разбан|апелляц|обжал|unban|appeal|возврат|refund|взлом|hacked|құпиясөз|parol|парол|бұз|буз|қайтар|qaytar|бұғат|блокла|blokla|бан|мут",
    re.I,
)


def topics(text, server_lang=None):
    value = normalize_kazakh(text, server_lang)
    return [k for k, p in PATTERNS.items() if p.search(value)]


def baseline_category(request):
    tags = topics(request.text, request.server_lang)
    if request.kind == "complaint":
        for tag in ("admin", "rmt_ads", "cheat", "scam", "insult", "dm"):
            if tag in tags:
                return "complaint." + tag
        return (
            "complaint.invalid"
            if len(request.text.strip()) < 15 or "question" in tags
            else "complaint.other"
        )
    for tag, category in (
        ("payment", "payment"),
        ("account", "account"),
        ("help", "help"),
    ):
        if tag in tags:
            return "report." + category
    if set(tags) & {"admin", "rmt_ads", "cheat", "scam", "insult", "dm"}:
        return "report.complaint"
    return "report.question" if "question" in tags else "report.offtopic"


def priority(request, category):
    text = normalize_kazakh(request.text, request.server_lang)
    if category == "report.payment" or "payment" in topics(text) or URGENT.search(text):
        return "p0"
    if category in {"complaint.cheat", "complaint.rmt_ads"} or (
        request.kind == "complaint" and request.evidence_count
    ):
        return "p1"
    if category == "complaint.scam" and re.search(
        r"бизнес|дом|квартир|миллион|million|үй|uy|машин|авто", text, re.I
    ):
        return "p1"
    if category in {"report.offtopic", "report.question", "complaint.invalid"}:
        return "p3"
    return "p2"


def extract(request):
    text = request.text
    nick = request.reported_nick
    if not nick:
        match = re.search(
            r"\b[A-Za-z][A-Za-z0-9]{1,30}_[A-Za-z][A-Za-z0-9]{1,30}\b", text
        )
        nick = match[0] if match else None
    refs = re.findall(
        r"(?<!\d)\d{1,2}\.\d{1,2}(?:\.\d{1,2}){0,2}(?!\d)",
        request.rule_refs_raw + "\n" + text,
    )
    server = request.server
    if not server:
        match = re.search(
            r"(?:сервер\w*|server|сервері)\s*[:#№-]?\s*(\d{1,3})\b", text, re.I
        )
        server = match[1] if match else None
    return Extracted(
        nickname=nick,
        rule_refs=list(dict.fromkeys(refs)),
        has_evidence=request.evidence_count > 0,
        server=server,
    )


def human_gate(request, category, confidence, cited, intent):
    reasons = []
    text = normalize_kazakh(request.text, request.server_lang)
    if request.kind == "complaint" or category.startswith("complaint."):
        reasons.append("Жалобу и обстоятельства проверяет администратор")
    if category in {
        "report.account",
        "report.payment",
        "report.complaint",
        "report.help",
    }:
        reasons.append("Нужны проверка данных или действия сотрудника")
    if set(topics(text)) & {"account", "payment"}:
        reasons.append("В тексте есть персональная ситуация с аккаунтом или платежом")
    if PERSONAL.search(text):
        reasons.append("Аккаунт, платёж или пересмотр санкции требуют человека")
    if request.evidence_count:
        reasons.append("Изображения недоступны модели и не просматривались")
    if confidence < 0.65:
        reasons.append("Недостаточно уверенности для автоматического ответа")
    if category == "report.question" and not cited and intent != "smalltalk":
        reasons.append("Нет цитируемого источника для ответа об игре")
    if re.search(
        r"\b(?:человек|оператор|сотрудник|human|agent|xodim|маман)\b", text, re.I
    ):
        reasons.append("Запрошено участие сотрудника")
    return reasons
