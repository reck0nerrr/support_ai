# Сдача Grand Mobile Support Copilot

Реализован контракт организаторов: POST /triage и make predict используют один движок. FastAPI, PostgreSQL и React CRM сохранены. Основной результат — контрактный триаж, поиск источников и безопасный черновик. CRM, Telegram и предложения шаблонов — дополнительные возможности.

## Данные и запуск

Архив организаторов непубличный. Данные, предсказания на реальных обращениях и отчёты с примерами держите в private/, исключённой из Git. Не публикуйте их и соблюдайте срок удаления из условий кейса. В образ Docker исходные данные не копируются: используется read-only mount.

```bash
make import-handout HANDOUT=/путь/grand-support-copilot-handout-2026-10-27.tgz
```

Импортирует только пять ожидаемых обычных файлов; архивные пути и скрипты не выполняются. HANDOUT_DIR по умолчанию private/handout. Для нового окружения создайте .env на основе .env.example; существующую .env не перезаписывайте.

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=ваш_ключ
OPENAI_MODEL=gpt-6-luna
```

Для GPT-6 по умолчанию reasoning.effort=none ради задержки. OPENAI_REASONING_EFFORT переопределяет настройку. Один вызов, локальный BM25, до 8 источников / 10 000 символов (RAG_TOP_K, RAG_MAX_CHARS), ограниченный вывод. Реальный p95 проверяется на доступной квоте, не выводится из этих настроек.

```bash
docker compose up -d --build
docker compose exec api python -m app.cli create-staff --login admin --name Admin
```

CRM и /triage: http://localhost:8080. Пароль вводится при создании. Если учётная запись уже существует и пароль забыт:

```bash
docker compose exec api python -m app.cli reset-password --login admin
```

Команда запросит новый пароль от 12 символов и отзовёт старые сессии. Пароль сам по себе нигде не выводится. Импортированные правила доступны движку сразу; seed-rules необязателен и добавляет их в редактор CRM. Telegram polling: docker compose --profile telegram up -d --build bot worker. Webhook и polling одновременно не используют.

## Прогон и отчёт

```bash
make predict IN=private/handout/tickets_valid.jsonl OUT=private/pred.jsonl
make evaluate GOLD=private/handout/tickets_valid.jsonl PRED=private/pred.jsonl \
  REPORT=private/evaluation.json MARKDOWN=private/evaluation.md KIND=organizer
```

БД не нужна для этих двух команд. PERSIST=1 дополнительно сохраняет прогоны/отчёты в настроенной PostgreSQL. В Docker файлы handout доступны как /data/handout; результат пишите в /tmp и заберите через docker compose cp.

Проверьте доступную квоту заранее. Batch соблюдает PREDICT_RPM=12, распознаёт дневную/платёжную квоту и длительный Retry-After; вместо повторов часами сохраняет явные ошибки для оставшихся строк. Изменение API-ключа в том же проекте само по себе не означает увеличения квоты.

Для проверки инфраструктуры без API:

```bash
AI_PROVIDER=offline make predict IN=private/handout/tickets_valid.jsonl OUT=private/valid.offline.pred.jsonl
AI_PROVIDER=offline make predict IN=datasets/contract.tickets.jsonl OUT=private/synthetic.pred.jsonl
make evaluate GOLD=datasets/contract.gold.jsonl PRED=private/synthetic.pred.jsonl KIND=synthetic
```

Offline использует простую эвристику категории/приоритета и резервный ответ с needs_human=true, без содержательной генерации. Это не показатель качества LLM. Новый синтетический набор содержит 22 самостоятельных сценария; прежний dev.* относится к старой таксономии.

## Честная оценка

В реальном valid нет меток категории и приоритета. Поэтому Accuracy и macro-F1 показывают «нет данных», пока не добавлена разметка. verdict, punishment, violation — исходы, не категории. Поле lang — эвристика, не эталон языка. Ответы администратора исключены из модели до сериализации промпта.

Подготовка 120 примеров для ручной разметки, со стратификацией по языковой подсказке и каналу:

```bash
make annotation-sample IN=private/handout/tickets_valid.jsonl OUT=private/annotations.pending.jsonl
```

Заполните category, priority, language, needs_human и поменяйте label_source на manual. Размечайте независимо от предсказаний, по возможности двумя людьми. Для ссылок можно добавить rule_ids с внутренними ключами раздел+пункт. Отсутствие поля исключает пример из precision/recall ссылок; [] означает, что ссылки не нужны. Не подставляйте эвристические/LLM-метки как человеческий эталон.

Ручная оценка черновиков — отдельный JSONL: ticket_id, correctness/usefulness/language/grounding (целые 1–5), citations_supported (boolean). Передайте --reviews в app.evaluate либо загрузите в CRM. Естественность KK/UZ должны проверить носители. Confidence модели не заменяет эту оценку.

Метрики: Accuracy категории, macro-F1 приоритета; язык только по ручным меткам; доля/precision/recall needs_human; существование и редакция источника; ручная оценка релевантности; стоимость по usage и тарифу для всех попыток; p50/p95 успешных вызовов и ошибок отдельно. Нет usage — неизвестная стоимость, а не ноль. Цели: $0,002 и p95 5 секунд. Не делайте вывод по быстрому отказу 429.

В CRM «Качество и стоимость» есть распределение 14 категорий, p0–p3, вызовы по языкам и загрузка отчётов. Можно загрузить неразмеченный valid и pred: runtime будет рассчитан, качество останется без оценки. Файлы до 8 МБ, суммарный запрос nginx до 16 МБ; больше — CLI с --persist.

## Бонусные шаблоны

```bash
make suggest-templates IN=private/handout/tickets_train.jsonl.gz OUT=private/templates.candidates.jsonl
```

Группирует повторяющиеся вопросы, предлагает частые исторические ответы и требует проверки. Никаких вызовов LLM и автоматической публикации в базу знаний. Исторические ответы могут обещать санкции или быть устаревшими — движок не использует их как готовые ответы.

RAG использует все 11 разделов rules.json, включая справочный раздел RP. Номера пунктов разделяются по разделам. При отсутствии ответа о механике игры сервис честно требует человека. Пополнение базы знаний из шаблонов — после проверки, не по частоте ответа.
