"""A small offline hint, not a replacement for the model's language detection."""

import re

LANGUAGES = {"ru", "en", "kk", "uz", "es", "pt"}


def normalize_kazakh(text, server_lang=None):
    if server_lang == "kk" or re.search(r"[ќґѕєјїЌҐЅЄЈЇ]", text):
        return text.translate(str.maketrans("ќґѕєјўїЌҐЅЄЈЎЇ", "қғңәөұүҚҒҢӘӨҰҮ"))
    return text


def language_hint(text):
    value = (
        normalize_kazakh(text)
        .lower()
        .replace("’", "'")
        .replace("ʻ", "'")
        .replace("‘", "'")
    )
    uzbek = re.search(
        r"\b(salom|menga|mening|qanday|uchun|nima|o'yin\w*|qoida\w*|mumkin\w*|hisob\w*|iltimos|bo'ladimi|салом|менинг|қандай|нима|илтимос|ўйин\w*|ҳисоб\w*)\b",
        value,
    )
    kazakh = re.search(
        r"[әіңөұү]|\b(сәлем|мені|маған|ойын|қалай|неге|өтінем|қазақ)\w*", value
    )
    if uzbek or re.search(r"[ўҳ]", value):
        return "uz"
    if kazakh:
        return "kk"
    if re.search(r"[а-яё]", value):
        return "ru"
    if re.search(r"\b(olá|ola|obrigado|ajuda|minha|conta|como|não|voce|você)\b", value):
        return "pt"
    if re.search(r"\b(hola|gracias|ayuda|cuenta|comprar|dónde|quiero)\b", value):
        return "es"
    return "en"


def fallback_draft(language):
    return {
        "ru": "Здравствуйте! Для этого обращения нужна проверка сотрудником. Опишите, что произошло, и при необходимости укажите сервер, ник и время события. Не отправляйте пароль или коды входа.",
        "en": "Hello! A support specialist needs to review this request. Describe what happened and, if relevant, provide the server, nickname and incident time. Do not send passwords or login codes.",
        "kk": "Сәлеметсіз бе! Бұл өтінішті қолдау қызметінің маманы тексеруі қажет. Не болғанын сипаттап, қажет болса, серверді, кейіпкер атын және оқиға уақытын көрсетіңіз. Құпиясөзді немесе кіру кодтарын жібермеңіз.",
        "uz": "Salom! Bu murojaatni qo'llab-quvvatlash xodimi tekshirishi kerak. Nima bo'lganini tushuntiring, zarur bo'lsa server, personaj nomi va voqea vaqtini ko'rsating. Parol yoki kirish kodlarini yubormang.",
        "es": "¡Hola! Un especialista debe revisar esta solicitud. Explica lo ocurrido e indica el servidor, el nombre del personaje y la hora si corresponde. No envíes contraseñas ni códigos de acceso.",
        "pt": "Olá! Um especialista precisa analisar esta solicitação. Descreva o ocorrido e informe o servidor, nome do personagem e horário, se necessário. Não envie senhas nem códigos de acesso.",
    }[language]


def preserve_uzbek_script(text, original):
    if not re.search(r"[а-яёўҳқғ]", original.lower()) or re.search(
        r"[a-z]", original.lower()
    ):
        return text
    # Only offline templates use this mechanical conversion. The LLM writes naturally.
    for left, right in [
        ("o'", "ў"),
        ("g'", "ғ"),
        ("sh", "ш"),
        ("ch", "ч"),
        ("yo", "ё"),
        ("yu", "ю"),
        ("ya", "я"),
    ]:
        text = re.sub(left, right, text, flags=re.I)
    return text.translate(
        str.maketrans(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "абсдефгҳижклмнопқрстуввхйзАБСДЕФГҲИЖКЛМНОПҚРСТУВВХЙЗ",
        )
    )
