# Support Copilot · evaluation

Тип выборки: **synthetic**. Дата: 2026-10-31T10:31:50.558304+00:00
Провайдеры: {'openai': 2}; модели: {'gpt-6-luna': 2}

| Метрика | Значение |
| --- | ---: |
| Обращений в эталоне | 54 |
| Ошибок выполнения | 1 |
| Accuracy | 1.9% |
| Macro-F1 | 3.6% |
| Язык ответа | 1.9% |
| Доля needs_human | 100.0% |
| Recall needs_human | 100.0% |
| Валидность возвращённых ссылок | 100.0% |
| Отклонено ответов проверкой ссылок | 0 |
| p50 / p95 обработки, мс | 7746.0 / 10896.9 |
| Стоимость на обращение | неизвестна: нужен тариф и usage для каждого вызова |
| Покрытие расчётом стоимости | 50.0% |
| Успешный вызов с известным тарифом, USD | 0.000500925 (n=1) |
| p50 / p95 успешных вызовов, мс | 11247.0 / 11247.0 |
| Ожидание темпа JSONL, мс суммарно | 0 |

Оценка качества черновиков: ожидает ручной проверки; оценка не выдумывается.

## По языкам

| Язык | N | Accuracy | Macro-F1 | Язык ответа |
| --- | ---: | ---: | ---: | ---: |
| kk | 16 | 0.0% | 0.0% | 0.0% |
| ru | 18 | 5.6% | 7.1% | 5.6% |
| uz | 20 | 0.0% | 0.0% | 0.0% |

## Примеры черновиков

### trade-kk

Эталон: player · kk

Результат: other; needs_human=True; status=error

Сәлеметсіз бе! Бұл өтінішті қолдау қызметінің маманы тексеруі қажет. Не болғанын сипаттап, қажет болса, серверді, кейіпкер атын және оқиға уақытын көрсетіңіз. Құпиясөзді немесе кіру кодтарын жібермеңіз.

### trade-ru

Эталон: player · ru

Результат: player; needs_human=True; status=ok

Если при обмене Max_Freeman забрал вашу машину и вышел из игры, это может относиться к мошенничеству в отношении игрока [4.1]. Для подачи жалобы откройте раздел жалоб в меню выбора персонажа лаунчера, укажите ник игрока, что произошло, место и время, а также приложите скриншоты или видеоссылку: без доказательств жалобу могут отклонить [Как подать жалобу на игрока]. Укажите также ник вашего персонажа и приложите имеющиеся доказательства сделки.

4.1: https://support.grnd.gg/ru/articles/12974300-iv-%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0-%D0%BF%D0%BE%D0%BB%D1%8C%D0%B7%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F-%D0%B8%D0%B3%D1%80%D0%BE%D0%B2%D1%8B%D0%BC%D0%B8-%D0%B0%D0%BA%D0%BA%D0%B0%D1%83%D0%BD%D1%82%D0%B0%D0%BC%D0%B8-%D0%B8-%D0%BF%D0%B5%D1%80%D1%81%D0%BE%D0%BD%D0%B0%D0%B6%D0%B0%D0%BC%D0%B8
Как подать жалобу на игрока: https://support.grnd.gg/ru/articles/11071809-%D0%BA%D0%B0%D0%BA-%D0%BF%D0%BE%D0%B4%D0%B0%D1%82%D1%8C-%D0%B6%D0%B0%D0%BB%D0%BE%D0%B1%D1%83-%D0%BD%D0%B0-%D0%BD%D0%B0%D1%80%D1%83%D1%88%D0%B5%D0%BD%D0%B8%D0%B5-%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB-%D0%B4%D1%80%D1%83%D0%B3%D0%B8%D0%BC-%D0%B8%D0%B3%D1%80%D0%BE%D0%BA%D0%BE%D0%BC

### trade-uz

Эталон: player · uz

Предсказание отсутствует.

### dm-ru

Эталон: player · ru

Предсказание отсутствует.

### dm-kk

Эталон: player · kk

Предсказание отсутствует.

### dm-uz

Эталон: player · uz

Предсказание отсутствует.

### admin-ru

Эталон: admin · ru

Предсказание отсутствует.

### admin-kk

Эталон: admin · kk

Предсказание отсутствует.

### admin-uz

Эталон: admin · uz

Предсказание отсутствует.

## Ограничения

- Synthetic data is a development check, not an organizer or production benchmark.
- Existing source IDs do not prove semantic support; grounding requires manual review.
- Latency measures processing, excludes CRM queue wait; costs are token-price estimates, not invoices.
- Offline results do not measure LLM quality; mixed model/prompt/corpus runs must be interpreted separately.
