# Запуск Support Copilot

## Docker Compose

Понадобятся Docker Compose и порт 8080. Команды выполняются из корня проекта.

```bash
cp -n .env.example .env
make import-handout HANDOUT=/путь/grand-support-copilot-handout-2026-10-27.tgz
docker compose up --build -d
docker compose exec api python -m app.cli create-staff --login admin --name "Администратор" --role admin
docker compose exec api python -m app.cli seed-rules
```

Создание сотрудника запросит пароль от 12 символов. Встроенных паролей и публичной регистрации нет. CRM: [localhost:8080](http://localhost:8080). Docker автоматически запускает миграции перед backend и worker. PostgreSQL и backend не публикуют свои порты наружу; frontend привязан к loopback.

Пустые поля `.env` используют значения по умолчанию: `ENVIRONMENT=development`, `PUBLIC_ORIGIN=http://localhost:8080`, `COOKIE_SECURE=false`, `AI_PROVIDER=offline`, `DEMO_ENABLED=false`. Compose по умолчанию создаёт локальную БД `copilot` с пользователем и паролем `copilot`. Перед боевым запуском задайте отдельный пароль PostgreSQL и секреты.

Для демонстрации задайте в `.env` `DEMO_ENABLED=true`, затем:

```bash
docker compose up -d
docker compose exec api python -m app.cli seed-demo
```

Четыре вымышленные жалобы помечены «демо». Ответы на них сохраняются в CRM без отправки Telegram. Администратор также может создавать тестовые жалобы и вопросы кнопкой в CRM.

Создание оператора с доступом к серверу:

```bash
docker compose exec api python -m app.cli create-staff --login operator --name "Оператор" --role operator --servers "Сервер 01"
```

Имена серверов должны совпадать с профилями игроков. Оператор без серверов не видит обращения; обращения без персонажа видит администратор. Роли: `admin`, `senior`, `operator`.

## Telegram

Создайте бота через BotFather и сохраните `TELEGRAM_BOT_TOKEN` в `.env`. Запустите polling:

```bash
docker compose --profile telegram up -d
```

Для polling публичный адрес не нужен. Если у бота уже есть webhook, сначала удалите его через Telegram Bot API. Код сам не меняет существующий webhook. Запускайте только один polling-процесс на бота.

Для webhook задайте случайный `TELEGRAM_WEBHOOK_SECRET`. Зарегистрируйте HTTPS URL `/api/telegram/webhook` через `setWebhook`, указав то же значение в `secret_token`. Backend проверяет `X-Telegram-Bot-Api-Secret-Token`. Polling в этом режиме не запускается. Не помещайте токен бота в React или публичные URL.

| Действие | Команда |
| --- | --- |
| Задать вопрос | Обычное текстовое сообщение |
| Добавить или выбрать персонажа | `/profile Сервер 01 \| Alex_Walker` |
| Список персонажей | `/profiles` |
| Создать жалобу | `/new` |
| Проверить и отправить жалобу | `/preview`, затем `/send` |
| Отменить создание | `/cancel` |
| Мои обращения | `/tickets`, `/ticket 1` |
| Дополнить обращение | `/reply 1 текст` |
| Язык ответа | `/language auto`, `/language ru`, `/language en`, `/language kk`, `/language uz` |
| Справка | `/help` |

Игровой ник не подтверждает владение аккаунтом. Полноценная проверка требует API или одноразового кода из игры; пароли бот не запрашивает. Жалобу о потере доступа можно подать без персонажа. В апелляции можно указать свою предыдущую жалобу.

Вложения до 20 МБ сохраняются как Telegram `file_id` и доступны сотруднику через защищённый endpoint. При создании — максимум 10 файлов. Большое видео отправляется ссылкой. Независимое S3-архивирование пока не подключено.

## LLM и автоответы

Задайте `AI_PROVIDER=openai`, `OPENAI_API_KEY`, `OPENAI_MODEL` — модель, доступную вашему аккаунту и поддерживающую Responses structured outputs. Затем `docker compose up -d` пересоздаст сервисы с новым окружением. При включении внешней модели текст обращений передаётся провайдеру. API использует `store=false`; внутренние комментарии в модель не передаются.

`AUTO_REPLY_ENABLED=true` разрешает LLM отвечать на простые вопросы, приветствия и безобидный абсурд. Для фактических ответов об игре нужны утверждённые источники. Для жалоб через `/new`, санкций, платежей, действий с аккаунтом, вложений и неоднозначных ситуаций требуется сотрудник. Если сотрудник взял обращение или игрок дополнил его, ещё не отправленный автоответ отменяется.

Все вопросы, разборы, автоответы и результаты доставки сохраняются. В CRM автор автоответа отмечен как `Support Copilot`. Флаг `AUTO_REPLY_ENABLED=false` отключает самостоятельную отправку. В режиме `offline` LLM не вызывается и автоответов нет — отображаются исходный текст и шаблон для сотрудника.

Команда `seed-rules` добавляет пункты из импортированного handout в редактор CRM. Движок использует read-only корпус handout и локальный поиск релевантных источников. Одинаковые номера различаются по разделам. Подробности сдачи и метрик — в [hackathon.md](hackathon.md).

Документация: [OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), [Telegram Bot API](https://core.telegram.org/bots/api).

## Разработка без Docker

Нужны Python 3.13+, Node 20.19+ и PostgreSQL 17. Создайте БД и задайте `DATABASE_URL` в `.env`. Для Vite укажите `PUBLIC_ORIGIN=http://localhost:5173`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-dev.txt
.venv/bin/alembic -c backend/alembic.ini upgrade head
PYTHONPATH=backend .venv/bin/python -m app.cli create-staff --login admin --name "Администратор"
```

В отдельных терминалах из корня проекта:

```bash
PYTHONPATH=backend .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000 --no-access-log
PYTHONPATH=backend .venv/bin/python -m app.worker
PYTHONPATH=backend .venv/bin/python -m app.polling
```

Бот запускается при наличии токена. Для frontend:

```bash
cd frontend
npm ci
npm run dev
```

CRM: [localhost:5173](http://localhost:5173). Документация API: [localhost:8000/docs](http://localhost:8000/docs). Для `npm run preview` измените `PUBLIC_ORIGIN` на адрес preview и перезапустите API.

## Проверки и резервное копирование

```bash
.venv/bin/pytest -q
cd frontend
npm run build
```

По умолчанию тесты работают в изолированной SQLite. Для PostgreSQL создайте отдельную БД **copilot_test** и запустите из корня:

```bash
TEST_DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/copilot_test .venv/bin/pytest -q
```

Тесты очищают указанную тестовую базу; имя `copilot_test` проверяется. Внешние API подменяются тестовыми ответами. Для живой интеграционной проверки нужны реальные ключи.

Резервная копия и восстановление в отдельную базу:

```bash
docker compose exec -T db pg_dump -U copilot -d copilot -Fc > copilot-backup.dump
docker compose exec db createdb -U copilot copilot_restore_check
docker compose exec -T db pg_restore -U copilot -d copilot_restore_check --no-owner < copilot-backup.dump
```

Храните копии вне сервера с ограничением доступа. Остановка: `docker compose --profile telegram down` сохраняет volume. Не добавляйте `-v`, если нужно сохранить жалобы.

До публичного запуска задайте `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `PUBLIC_ORIGIN=https://ваш-домен`, `DEMO_ENABLED=false`, настройте TLS reverse proxy, секреты, мониторинг и сроки хранения данных. Смена `POSTGRES_PASSWORD` в `.env` сама по себе не меняет пароль в уже созданном volume. Для неинтерактивного создания сотрудника CLI поддерживает `COPILOT_STAFF_PASSWORD` через окружение.

## Triage и оценка

Добавлены `POST /triage` и `make predict IN=tickets.jsonl OUT=pred.jsonl`. [Контракт организаторов](triage-contract.md), [прогон и метрики](hackathon.md). Перед обновлением нативного запуска примените миграции. В production задайте отдельный `TRIAGE_API_KEY`; клиент triage передаёт его как Bearer-токен.

Новые Telegram-профили используют `language=auto`: язык ответа определяется по тексту игрока независимо от языка интерфейса Telegram. Явный выбор через `/language` сохраняется; `/language auto` возвращает автоматическое определение. Для существующих профилей прежнее предпочтение сохраняется до смены команды.

Для сброса забытого пароля: `docker compose exec api python -m app.cli reset-password --login admin`. Новый пароль вводится интерактивно, существующие сессии отзываются.
