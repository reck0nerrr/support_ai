import argparse
import getpass
import os
from sqlalchemy import delete, select
from .config import settings
from .db import session_factory
from .models import AuthSession, Player, Profile, Rule, Staff, Ticket
from .security import hash_password
from .services import create_ticket
from .knowledge import bundled_rules

# Paraphrases of official help pages, imported as unapproved reference articles.
SOURCES = [
    {
        "title": "Как подать жалобу на игрока",
        "version": "2025-04-11",
        "url": "https://support.grnd.gg/ru/articles/11071809",
        "text": "Для жалобы на игрока укажите ник участника и обстоятельства события: что произошло, где и когда. Приложите скриншоты или ссылку на видео. Недостаток доказательств может помешать рассмотрению. Для обращения важен персонаж, которого касается инцидент.",
    },
    {
        "title": "Апелляция на санкцию или решение",
        "version": "2025-04-11",
        "url": "https://support.grnd.gg/ru/articles/11071824",
        "text": "При обжаловании укажите администратора, номер исходной жалобы при его наличии и основания для пересмотра. Добавьте материалы, объясняющие несогласие. Проверку и решение выполняет уполномоченный сотрудник проекта.",
    },
    {
        "title": "Жалобы и доказательства",
        "version": "2025-04-11",
        "url": "https://support.grnd.gg/ru/articles/11071798",
        "text": "Игрок может сообщить администрации о предполагаемом нарушении, включая оскорбления, мошенничество и использование сторонних программ. Скриншоты и видеозаписи помогают установить обстоятельства. Само обращение не доказывает нарушение.",
    },
]

DEMOS = [
    (
        "Alex_Walker",
        "Сервер 01",
        "player",
        "Обман при обмене автомобилями",
        "Сегодня около 18:30 на парковке у автосалона игрок Max_Freeman обещал обменять Sultan на мой автомобиль. После передачи он вышел из игры. Сервер 01. Прошу проверить сделку. Скриншотов нет, запись сохранилась у друга.",
    ),
    (
        "Mila_Rose",
        "Сервер 03",
        "appeal",
        "Прошу пересмотреть блокировку",
        "Не согласна с блокировкой персонажа от администратора Anton_Black. Наказание выдано вчера в 21:10. Считаю, что произошла ошибка: в момент события была на работе в игре. Прошу проверить логи и уточнить причину санкции.",
    ),
    (
        "Nikita_Volkov",
        "Сервер 01",
        "technical",
        "Игра закрывается при входе",
        "После последнего обновления игра закрывается на загрузке персонажа. Android 14, Samsung A54. Пробовал перезапуск и другую сеть. Ошибки на экране нет. Как восстановить вход без потери прогресса?",
    ),
    (
        "Denis_Stone",
        "Сервер 07",
        "payment",
        "Покупка не появилась на аккаунте",
        "Вчера оплатил покупку через магазин приложения. Платёж списался, но товар пока не появился. Чек могу приложить сотруднику. Ник Denis_Stone, сервер 07. Помогите проверить, куда поступила покупка.",
    ),
]


def seed_rules(db):
    for source in bundled_rules():
        if not db.get(Rule, source["id"]):
            db.add(
                Rule(
                    **{
                        k: v
                        for k, v in source.items()
                        if k
                        in {"id", "title", "clause", "url", "version", "text", "server"}
                    },
                    approved=True,
                )
            )
    for item in SOURCES:
        if not db.scalar(
            select(Rule).where(Rule.url == item["url"], Rule.version == item["version"])
        ):
            db.add(Rule(**item, approved=False))


def main():
    parser = argparse.ArgumentParser(description="Support Copilot administration")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-staff")
    create.add_argument("--login", required=True)
    create.add_argument("--name", required=True)
    create.add_argument(
        "--role", choices=["admin", "senior", "operator"], default="admin"
    )
    create.add_argument(
        "--servers", default="", help="Comma-separated exact server names"
    )
    reset = sub.add_parser("reset-password")
    reset.add_argument("--login", required=True)
    sub.add_parser("seed-rules")
    sub.add_parser("seed-demo")
    args = parser.parse_args()
    with session_factory()() as db, db.begin():
        if args.command in {"create-staff", "reset-password"}:
            existing = db.scalar(select(Staff).where(Staff.login == args.login))
            if args.command == "create-staff" and existing:
                raise SystemExit("Login already exists")
            if args.command == "reset-password" and not existing:
                raise SystemExit("Login does not exist")
            password = os.environ.get("COPILOT_STAFF_PASSWORD") or getpass.getpass(
                "Password (12+ characters): "
            )
            if len(password) < 12 or len(password) > 200:
                raise SystemExit("Password must contain 12–200 characters")
            if args.command == "reset-password":
                existing.password_hash = hash_password(password)
                db.execute(
                    delete(AuthSession).where(AuthSession.staff_id == existing.id)
                )
                print("Password updated; existing sessions revoked")
                return
            db.add(
                Staff(
                    login=args.login,
                    name=args.name,
                    role=args.role,
                    servers=[s.strip() for s in args.servers.split(",") if s.strip()],
                    password_hash=hash_password(password),
                )
            )
            print("Staff account created")
        elif args.command == "seed-rules":
            seed_rules(db)
            print(
                "Reviewed bundled rules added; legacy help drafts still await approval"
            )
        elif args.command == "seed-demo":
            if not settings().demo_enabled or settings().environment == "production":
                raise SystemExit("Demo is disabled")
            if db.scalar(select(Ticket).where(Ticket.demo.is_(True))):
                print("Demo tickets already exist")
                return
            seed_rules(db)
            for nickname, server, category, title, text in DEMOS:
                player = Player(name=nickname, language="ru")
                db.add(player)
                db.flush()
                profile = Profile(player_id=player.id, nickname=nickname, server=server)
                db.add(profile)
                db.flush()
                ticket = create_ticket(db, player, profile, text, category, demo=True)
                ticket.title = title
            print(
                "Four synthetic demo complaints created; no Telegram messages will be sent"
            )


if __name__ == "__main__":
    main()
