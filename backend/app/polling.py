"""Local Telegram entry point. Use one poller per bot, or use the webhook instead."""

import time
import httpx
from sqlalchemy import func, select
from .config import settings
from .db import session_factory
from .models import TelegramUpdate
from .telegram import handle_update


def main():
    token = settings().telegram_bot_token
    if not token:
        raise SystemExit("Set TELEGRAM_BOT_TOKEN")
    with httpx.Client(timeout=40) as client:
        info = client.get(f"https://api.telegram.org/bot{token}/getWebhookInfo").json()
        if not info.get("ok") or info["result"].get("url"):
            raise SystemExit(
                "Polling unavailable: inspect/remove the existing webhook first"
            )
        with session_factory()() as db:
            offset = (db.scalar(select(func.max(TelegramUpdate.update_id))) or 0) + 1
        while True:
            try:
                body = client.get(
                    f"https://api.telegram.org/bot{token}/getUpdates",
                    params={
                        "offset": offset,
                        "timeout": 25,
                        "allowed_updates": '["message"]',
                    },
                ).json()
                if not body.get("ok"):
                    time.sleep(5)
                    continue
                for update in body["result"]:
                    with session_factory()() as db, db.begin():
                        handle_update(db, update)
                    offset = update["update_id"] + 1
            except (httpx.HTTPError, ValueError):
                time.sleep(5)


if __name__ == "__main__":
    main()
