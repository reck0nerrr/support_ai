# Support Copilot · evaluation

Тип выборки: **synthetic**. Дата: 2026-10-30T17:07:02.538139+00:00
Провайдеры: {'offline': 54}; модели: {'offline-template': 54}

| Метрика | Значение |
| --- | ---: |
| Обращений в эталоне | 54 |
| Ошибок выполнения | 0 |
| Accuracy | 48.1% |
| Macro-F1 | 9.3% |
| Язык ответа | 96.3% |
| Доля needs_human | 100.0% |
| Recall needs_human | 100.0% |
| Валидность возвращённых ссылок | нет данных |
| Отклонено ответов проверкой ссылок | 0 |
| p50 / p95 обработки, мс | 2.0 / 4.35 |
| Стоимость на обращение | $0.00000000 |
| Покрытие расчётом стоимости | 100.0% |
| Успешный вызов с известным тарифом, USD | 0.0 (n=54) |
| p50 / p95 успешных вызовов, мс | 2.0 / 4.35 |
| Ожидание темпа JSONL, мс суммарно | 0 |

Оценка качества черновиков: ожидает ручной проверки; оценка не выдумывается.

## По языкам

| Язык | N | Accuracy | Macro-F1 | Язык ответа |
| --- | ---: | ---: | ---: | ---: |
| kk | 16 | 50.0% | 9.5% | 100.0% |
| ru | 18 | 50.0% | 9.5% | 100.0% |
| uz | 20 | 45.0% | 8.9% | 90.0% |

## Примеры черновиков

### trade-kk

Эталон: player · kk

Результат: other; needs_human=True; status=ok

Сәлеметсіз бе! Бұл өтінішті қолдау қызметінің маманы тексеруі қажет. Не болғанын сипаттап, қажет болса, серверді, кейіпкер атын және оқиға уақытын көрсетіңіз. Құпиясөзді немесе кіру кодтарын жібермеңіз.

### trade-ru

Эталон: player · ru

Результат: other; needs_human=True; status=ok

Здравствуйте! Для этого обращения нужна проверка сотрудником. Опишите, что произошло, и при необходимости укажите сервер, ник и время события. Не отправляйте пароль или коды входа.

### trade-uz

Эталон: player · uz

Результат: other; needs_human=True; status=ok

Salom! Bu murojaatni qo'llab-quvvatlash xodimi tekshirishi kerak. Nima bo'lganini tushuntiring, zarur bo'lsa server, personaj nomi va voqea vaqtini ko'rsating. Parol yoki kirish kodlarini yubormang.

### dm-ru

Эталон: player · ru

Результат: other; needs_human=True; status=ok

Здравствуйте! Для этого обращения нужна проверка сотрудником. Опишите, что произошло, и при необходимости укажите сервер, ник и время события. Не отправляйте пароль или коды входа.

### dm-kk

Эталон: player · kk

Результат: other; needs_human=True; status=ok

Сәлеметсіз бе! Бұл өтінішті қолдау қызметінің маманы тексеруі қажет. Не болғанын сипаттап, қажет болса, серверді, кейіпкер атын және оқиға уақытын көрсетіңіз. Құпиясөзді немесе кіру кодтарын жібермеңіз.

### dm-uz

Эталон: player · uz

Результат: other; needs_human=True; status=ok

Hello! A support specialist needs to review this request. Describe what happened and, if relevant, provide the server, nickname and incident time. Do not send passwords or login codes.

### admin-ru

Эталон: admin · ru

Результат: other; needs_human=True; status=ok

Здравствуйте! Для этого обращения нужна проверка сотрудником. Опишите, что произошло, и при необходимости укажите сервер, ник и время события. Не отправляйте пароль или коды входа.

### admin-kk

Эталон: admin · kk

Результат: other; needs_human=True; status=ok

Сәлеметсіз бе! Бұл өтінішті қолдау қызметінің маманы тексеруі қажет. Не болғанын сипаттап, қажет болса, серверді, кейіпкер атын және оқиға уақытын көрсетіңіз. Құпиясөзді немесе кіру кодтарын жібермеңіз.

### admin-uz

Эталон: admin · uz

Результат: other; needs_human=True; status=ok

Salom! Bu murojaatni qo'llab-quvvatlash xodimi tekshirishi kerak. Nima bo'lganini tushuntiring, zarur bo'lsa server, personaj nomi va voqea vaqtini ko'rsating. Parol yoki kirish kodlarini yubormang.

## Ограничения

- Synthetic data is a development check, not an organizer or production benchmark.
- Existing source IDs do not prove semantic support; grounding requires manual review.
- Latency measures processing, excludes CRM queue wait; costs are token-price estimates, not invoices.
- Offline results do not measure LLM quality; mixed model/prompt/corpus runs must be interpreted separately.
