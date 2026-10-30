"""Transactional bot dialog; all responses use the durable outbox."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .models import BotState, Player, Profile, TelegramUpdate, Ticket
from .services import create_ticket, enqueue, player_message

CATEGORIES = {
    "1": "player",
    "2": "admin",
    "3": "appeal",
    "4": "account",
    "5": "payment",
    "6": "technical",
    "7": "other",
}
HELP = (
    "Support Copilot · Grand Mobile\n\n"
    "Напишите вопрос обычным сообщением. На простые вопросы Copilot может ответить сам; сложные передаст сотруднику. Переписка сохраняется.\n\n"
    "/profile сервер | Nick_Name — добавить или выбрать персонажа (без проверки владения)\n"
    "/profiles — мои персонажи\n/new — новое обращение\n/tickets — мои обращения\n"
    "/ticket номер — история\n/reply номер текст — дополнить обращение\n"
    "/language ru или en — язык ответа\n/cancel — отменить создание\n\n"
    "При потере аккаунта можно обратиться без привязки. Ник не подтверждает владение. Пароль от игры не нужен."
)


def tell(db, chat, text):
    enqueue(db, "telegram", {"chat_id": chat, "text": text[:4000]})


def extract_files(message):
    result = []
    if message.get("photo"):
        p = message["photo"][-1]
        result.append(
            {
                "name": "screenshot.jpg",
                "file_id": p["file_id"],
                "mime": "image/jpeg",
                "size": p.get("file_size", 0),
            }
        )
    document = message.get("document") or message.get("video")
    if document:
        result.append(
            {
                "name": document.get("file_name", "evidence")[:200],
                "file_id": document["file_id"],
                "mime": document.get("mime_type", "application/octet-stream")[:100],
                "size": document.get("file_size", 0),
            }
        )
    return result


def handle_update(db, update):
    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return False
    if db.get(TelegramUpdate, update_id):
        return False
    # The unique insert serializes duplicate delivery; it is committed with all domain changes.
    try:
        with db.begin_nested():
            db.add(TelegramUpdate(update_id=update_id))
            db.flush()
    except IntegrityError:
        return False
    m = update.get("message", {})
    sender = m.get("from", {})
    if not sender.get("id") or m.get("chat", {}).get("type") != "private":
        return True
    chat = m["chat"]["id"]
    player = db.scalar(
        select(Player).where(Player.telegram_id == sender["id"]).with_for_update()
    )
    if not player:
        player = Player(
            telegram_id=sender["id"],
            name=str(sender.get("first_name", "Игрок"))[:100],
            language="en" if sender.get("language_code", "").startswith("en") else "ru",
        )
        db.add(player)
        db.flush()
    state = db.get(BotState, player.id)
    if not state:
        state = BotState(player_id=player.id, step="idle", data={})
        db.add(state)
    text = (m.get("text") or m.get("caption") or "").strip()[:10000]
    command, _, argument = text.partition(" ")
    command = command.split("@")[0].lower()
    files = extract_files(m)
    if any(f["size"] > 20 * 1024 * 1024 for f in files):
        tell(
            db,
            chat,
            "Размер файла — не более 20 МБ. Для большого видео отправьте ссылку.",
        )
        return True
    if command in {"/start", "/help"}:
        tell(db, chat, HELP)
    elif command == "/language":
        if argument not in {"ru", "en"}:
            tell(db, chat, "/language ru или /language en")
        else:
            player.language = argument
            tell(db, chat, "Язык ответа сохранён / Reply language saved.")
    elif command == "/profile":
        parts = [p.strip() for p in argument.split("|", 1)]
        if (
            len(parts) != 2
            or not all(parts)
            or len(parts[0]) > 80
            or len(parts[1]) > 100
        ):
            tell(db, chat, "Формат: /profile сервер | Nick_Name")
        elif len(
            db.scalars(select(Profile).where(Profile.player_id == player.id)).all()
        ) >= 10 and not db.scalar(
            select(Profile).where(
                Profile.player_id == player.id,
                Profile.server == parts[0],
                Profile.nickname == parts[1],
            )
        ):
            tell(db, chat, "Можно добавить до 10 персонажей.")
        else:
            profile = db.scalar(
                select(Profile).where(
                    Profile.player_id == player.id,
                    Profile.server == parts[0],
                    Profile.nickname == parts[1],
                )
            )
            if not profile:
                profile = Profile(
                    player_id=player.id, server=parts[0], nickname=parts[1]
                )
                db.add(profile)
                db.flush()
            if state.profile_id != profile.id:
                state.data = {
                    key: value
                    for key, value in state.data.items()
                    if key != "chat_ticket"
                }
            state.profile_id = profile.id
            tell(
                db,
                chat,
                f"Выбран {profile.nickname} · {profile.server}. Владение не подтверждено.",
            )
    elif command == "/profiles":
        profiles = db.scalars(
            select(Profile).where(Profile.player_id == player.id)
        ).all()
        tell(
            db,
            chat,
            "\n".join(f"{p.server} | {p.nickname}" for p in profiles)
            or "Персонажей пока нет. /profile сервер | Nick_Name",
        )
    elif command == "/cancel":
        state.step, state.data = "idle", {}
        tell(db, chat, "Создание обращения отменено.")
    elif command == "/new":
        state.step, state.data = "category", {}
        tell(
            db,
            chat,
            "Выберите категорию, отправив цифру:\n1 — игрок\n2 — администратор\n3 — апелляция\n4 — аккаунт\n5 — платёж\n6 — техническая проблема\n7 — другое",
        )
    elif command == "/tickets":
        tickets = db.scalars(
            select(Ticket)
            .where(Ticket.player_id == player.id)
            .order_by(Ticket.updated_at.desc())
            .limit(20)
        ).all()
        tell(
            db,
            chat,
            "\n".join(f"#{t.id} · {t.status} · {t.title[:60]}" for t in tickets)
            or "Обращений пока нет. /new",
        )
    elif command in {"/ticket", "/reply"}:
        number, _, addition = argument.partition(" ")
        ticket = (
            db.scalar(
                select(Ticket)
                .where(Ticket.id == int(number), Ticket.player_id == player.id)
                .with_for_update()
            )
            if number.isdigit() and len(number) < 10
            else None
        )
        if not ticket:
            tell(db, chat, "Обращение не найдено.")
        elif command == "/reply":
            if not addition and not files:
                tell(
                    db,
                    chat,
                    "Формат: /reply номер дополнение (можно в подписи к вложению)",
                )
            else:
                player_message(
                    db, ticket, addition or "Дополнительные материалы", files
                )
                tell(db, chat, f"Дополнение к #{ticket.id} сохранено.")
        else:
            from .models import Message

            messages = db.scalars(
                select(Message)
                .where(
                    Message.ticket_id == ticket.id,
                    Message.author.in_(["player", "staff", "assistant"]),
                )
                .order_by(Message.created_at.desc())
                .limit(8)
            ).all()
            visible = [
                v
                for v in reversed(messages)
                if v.author == "player" or v.delivery in {"sent", "demo"}
            ]
            tell(
                db,
                chat,
                f"#{ticket.id} · {ticket.status}\n"
                + "\n\n".join(
                    f"{'Вы' if v.author == 'player' else 'Поддержка'}: {v.text}"
                    for v in visible
                )[-3500:],
            )
    elif state.step == "category" and text in CATEGORIES:
        state.data = {"category": CATEGORIES[text], "files": []}
        state.step = "parent" if text == "3" else "description"
        tell(
            db,
            chat,
            "Номер предыдущей жалобы или /skip, если её нет в этой системе."
            if text == "3"
            else "Опишите, что произошло: участники, место, дата и время. Для платежа не присылайте полные реквизиты карты или пароль.",
        )
    elif state.step == "parent":
        parent = (
            db.scalar(
                select(Ticket).where(
                    Ticket.id == int(text), Ticket.player_id == player.id
                )
            )
            if text.isdigit() and len(text) < 10
            else None
        )
        if text != "/skip" and not parent:
            tell(db, chat, "Укажите номер своей жалобы или /skip.")
        else:
            state.data = {**state.data, "parent_id": parent.id if parent else None}
            state.step = "description"
            tell(
                db,
                chat,
                "Опишите основание апелляции, имя администратора, дату и обстоятельства.",
            )
    elif state.step == "description" and len(text) >= 10 and not text.startswith("/"):
        state.data = {**state.data, "text": text, "files": files}
        state.step = "evidence"
        tell(
            db,
            chat,
            "Пришлите скриншоты, документы или ссылки на видео. Затем /preview. Если материалов нет — /preview сразу.",
        )
    elif state.step == "evidence":
        if command == "/preview":
            profile = db.get(Profile, state.profile_id) if state.profile_id else None
            state.step = "confirm"
            tell(
                db,
                chat,
                f"Проверьте обращение\nПерсонаж: {profile.nickname + ' · ' + profile.server if profile else 'не указан'}\nВложений: {len(state.data.get('files', []))}\n\n{state.data['text'][:2800]}\n\n/send — отправить\n/cancel — отменить",
            )
        elif not text.startswith("/") and (text or files):
            if (
                len(state.data.get("files", [])) + len(files) > 10
                or len(state.data.get("text", "")) + len(text) > 16000
            ):
                tell(
                    db,
                    chat,
                    "Лимит: 10 файлов и 16 000 символов на обращение. /preview — проверить.",
                )
            else:
                state.data = {
                    **state.data,
                    "text": state.data["text"] + ("\n" + text if text else ""),
                    "files": state.data.get("files", []) + files,
                }
                tell(db, chat, "Материалы добавлены. /preview — проверить обращение.")
        else:
            tell(db, chat, "/preview — проверить обращение, /cancel — отменить.")
    elif state.step == "confirm" and command == "/send":
        profile = db.get(Profile, state.profile_id) if state.profile_id else None
        ticket = create_ticket(
            db,
            player,
            profile,
            state.data["text"],
            state.data["category"],
            state.data.get("parent_id"),
            attachments=state.data.get("files", []),
        )
        state.step, state.data = "idle", {}
        tell(
            db,
            chat,
            f"Обращение #{ticket.id} принято. Его проверит сотрудник.\n/reply {ticket.id} текст — дополнить\n/tickets — статус",
        )
    elif state.step == "idle" and not text.startswith("/") and (text or files):
        profile = db.get(Profile, state.profile_id) if state.profile_id else None
        previous = state.data.get("chat_ticket")
        ticket = (
            db.scalar(
                select(Ticket)
                .where(Ticket.id == previous, Ticket.player_id == player.id)
                .with_for_update()
            )
            if previous
            else None
        )
        if ticket and ticket.intake == "chat" and ticket.status not in {"closed"}:
            player_message(db, ticket, text or "Материалы к вопросу", files)
        else:
            ticket = create_ticket(
                db,
                player,
                profile,
                text or "Материалы к вопросу",
                attachments=files,
                intake="chat",
            )
        state.data = {"chat_ticket": ticket.id}
    else:
        tell(
            db,
            chat,
            "/new — создать обращение, /help — команды. При создании следуйте текущему шагу или используйте /cancel.",
        )
    return True
