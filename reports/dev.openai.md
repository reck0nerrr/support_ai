# Support Copilot · evaluation

Тип выборки: **synthetic**. Дата: 2026-10-30T16:37:25.073751+00:00
Провайдеры: {'openai': 54}; модели: {'gpt-6-luna': 54}

| Метрика | Значение |
| --- | ---: |
| Обращений в эталоне | 54 |
| Ошибок выполнения | 23 |
| Accuracy | 57.4% |
| Macro-F1 | 81.3% |
| Язык ответа | 57.4% |
| Доля needs_human | 81.5% |
| Recall needs_human | 100.0% |
| Валидность возвращённых ссылок | 100.0% |
| Отклонено ответов проверкой ссылок | 0 |
| p50 / p95 обработки, мс | 2955.5 / 6138.7 |
| Стоимость на обращение | неизвестна: нужен тариф и usage для каждого вызова |
| Покрытие расчётом стоимости | 57.4% |
| Успешный вызов с известным тарифом, USD | 0.0004672073 (n=31) |
| p50 / p95 успешных вызовов, мс | 3815.0 / 6588.0 |
| Ожидание темпа JSONL, мс суммарно | 0 |

Оценка качества черновиков: ожидает ручной проверки; оценка не выдумывается.

## По языкам

| Язык | N | Accuracy | Macro-F1 | Язык ответа |
| --- | ---: | ---: | ---: | ---: |
| kk | 16 | 62.5% | 88.7% | 62.5% |
| ru | 18 | 55.6% | 85.2% | 55.6% |
| uz | 20 | 55.0% | 80.2% | 55.0% |

## Примеры черновиков

### trade-kk

Эталон: player · kk

Результат: player; needs_human=True; status=ok

Сипаттауыңыз бойынша, Max_Freeman көлік айырбастау кезінде көлігіңізді алып, ойыннан шығып кеткен болуы мүмкін. Ойыншыларды алдау ережемен тыйым салынған [4.1]. Шағымды лаунчердегі кейіпкер таңдау мәзірінің шағымдар бөлімінде беріп, ойыншының никін, 01-серверді, оқиға уақытын және скриншот не видео дәлелін қосыңыз [Как подать жалобу на игрока].

4.1: https://support.grnd.gg/ru/articles/12974300-iv-%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0-%D0%BF%D0%BE%D0%BB%D1%8C%D0%B7%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F-%D0%B8%D0%B3%D1%80%D0%BE%D0%B2%D1%8B%D0%BC%D0%B8-%D0%B0%D0%BA%D0%BA%D0%B0%D1%83%D0%BD%D1%82%D0%B0%D0%BC%D0%B8-%D0%B8-%D0%BF%D0%B5%D1%80%D1%81%D0%BE%D0%BD%D0%B0%D0%B6%D0%B0%D0%BC%D0%B8
Как подать жалобу на игрока: https://support.grnd.gg/ru/articles/11071809-%D0%BA%D0%B0%D0%BA-%D0%BF%D0%BE%D0%B4%D0%B0%D1%82%D1%8C-%D0%B6%D0%B0%D0%BB%D0%BE%D0%B1%D1%83-%D0%BD%D0%B0-%D0%BD%D0%B0%D1%80%D1%83%D1%88%D0%B5%D0%BD%D0%B8%D0%B5-%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB-%D0%B4%D1%80%D1%83%D0%B3%D0%B8%D0%BC-%D0%B8%D0%B3%D1%80%D0%BE%D0%BA%D0%BE%D0%BC

### trade-ru

Эталон: player · ru

Результат: player; needs_human=True; status=ok

Понимаем, что вы сообщаете о возможном мошенничестве при обмене. По правилам запрещено мошенничество в отношении игроков [4.1]. Чтобы оформить жалобу, в лаунчере откройте раздел жалоб и укажите ник персонажа, место, время и приложите скриншоты или видеоссылку; без доказательств жалобу могут отклонить [Как подать жалобу на игрока]. Укажите также ваш ник персонажа и приложите имеющиеся доказательства — для проверки потребуется рассмотрение человеком.

4.1: https://support.grnd.gg/ru/articles/12974300-iv-%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0-%D0%BF%D0%BE%D0%BB%D1%8C%D0%B7%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F-%D0%B8%D0%B3%D1%80%D0%BE%D0%B2%D1%8B%D0%BC%D0%B8-%D0%B0%D0%BA%D0%BA%D0%B0%D1%83%D0%BD%D1%82%D0%B0%D0%BC%D0%B8-%D0%B8-%D0%BF%D0%B5%D1%80%D1%81%D0%BE%D0%BD%D0%B0%D0%B6%D0%B0%D0%BC%D0%B8
Как подать жалобу на игрока: https://support.grnd.gg/ru/articles/11071809-%D0%BA%D0%B0%D0%BA-%D0%BF%D0%BE%D0%B4%D0%B0%D1%82%D1%8C-%D0%B6%D0%B0%D0%BB%D0%BE%D0%B1%D1%83-%D0%BD%D0%B0-%D0%BD%D0%B0%D1%80%D1%83%D1%88%D0%B5%D0%BD%D0%B8%D0%B5-%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB-%D0%B4%D1%80%D1%83%D0%B3%D0%B8%D0%BC-%D0%B8%D0%B3%D1%80%D0%BE%D0%BA%D0%BE%D0%BC

### trade-uz

Эталон: player · uz

Результат: player; needs_human=True; status=ok

Agar Max_Freeman almashuv paytida avtomobilingizni olib ketgan bo‘lsa, bu boshqa o‘yinchiga nisbatan firibgarlik bo‘lishi mumkin va qoidalarda taqiqlangan [4.1]. Bunday holatni tekshirtirish uchun launcherda personaj tanlash menyusidagi shikoyatlar bo‘limida shikoyat yarating; Max_Freeman nikini, 01-serverni, bugun 18:30 dagi voqeani va mavjud skrinshot yoki video havolasini kiriting [Как подать жалобу на игрока]. Shikoyatingizni ko‘rib chiqish uchun personajingiz nikini hamda mavjud dalillarni yuboring.

4.1: https://support.grnd.gg/ru/articles/12974300-iv-%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB%D0%B0-%D0%BF%D0%BE%D0%BB%D1%8C%D0%B7%D0%BE%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F-%D0%B8%D0%B3%D1%80%D0%BE%D0%B2%D1%8B%D0%BC%D0%B8-%D0%B0%D0%BA%D0%BA%D0%B0%D1%83%D0%BD%D1%82%D0%B0%D0%BC%D0%B8-%D0%B8-%D0%BF%D0%B5%D1%80%D1%81%D0%BE%D0%BD%D0%B0%D0%B6%D0%B0%D0%BC%D0%B8
Как подать жалобу на игрока: https://support.grnd.gg/ru/articles/11071809-%D0%BA%D0%B0%D0%BA-%D0%BF%D0%BE%D0%B4%D0%B0%D1%82%D1%8C-%D0%B6%D0%B0%D0%BB%D0%BE%D0%B1%D1%83-%D0%BD%D0%B0-%D0%BD%D0%B0%D1%80%D1%83%D1%88%D0%B5%D0%BD%D0%B8%D0%B5-%D0%BF%D1%80%D0%B0%D0%B2%D0%B8%D0%BB-%D0%B4%D1%80%D1%83%D0%B3%D0%B8%D0%BC-%D0%B8%D0%B3%D1%80%D0%BE%D0%BA%D0%BE%D0%BC

### rp-kk

Эталон: other · kk

Результат: other; needs_human=False; status=ok

RP (RolePlay) — рөлдік ойын: ойыншы ойдан шығарылған кейіпкердің рөлінде әрекет етеді [RP].

RP: https://support.grnd.gg/ru/articles/12974307-vi-%D1%82%D0%B5%D1%80%D0%BC%D0%B8%D0%BD%D1%8B-%D0%B8-%D0%B8%D1%85-%D0%BE%D0%BF%D0%B8%D1%81%D0%B0%D0%BD%D0%B8%D0%B5

### rp-ru

Эталон: other · ru

Результат: other; needs_human=False; status=ok

RP (RolePlay) — это игра по ролям: игрок действует от лица придуманного персонажа [RP].

RP: https://support.grnd.gg/ru/articles/12974307-vi-%D1%82%D0%B5%D1%80%D0%BC%D0%B8%D0%BD%D1%8B-%D0%B8-%D0%B8%D1%85-%D0%BE%D0%BF%D0%B8%D1%81%D0%B0%D0%BD%D0%B8%D0%B5

### rp-uz

Эталон: other · uz

Результат: other; needs_human=False; status=ok

Grand Mobile’da RP — bu RolePlay, ya’ni o‘ylab topilgan personaj rolida o‘ynash [RP].

RP: https://support.grnd.gg/ru/articles/12974307-vi-%D1%82%D0%B5%D1%80%D0%BC%D0%B8%D0%BD%D1%8B-%D0%B8-%D0%B8%D1%85-%D0%BE%D0%BF%D0%B8%D1%81%D0%B0%D0%BD%D0%B8%D0%B5

### nonsense-ru

Эталон: other · ru

Результат: other; needs_human=True; status=error

Здравствуйте! Для этого обращения нужна проверка сотрудником. Опишите, что произошло, и при необходимости укажите сервер, ник и время события. Не отправляйте пароль или коды входа.

### nonsense-kk

Эталон: other · kk

Результат: other; needs_human=True; status=error

Сәлеметсіз бе! Бұл өтінішті қолдау қызметінің маманы тексеруі қажет. Не болғанын сипаттап, қажет болса, серверді, кейіпкер атын және оқиға уақытын көрсетіңіз. Құпиясөзді немесе кіру кодтарын жібермеңіз.

### unknown-gameplay-ru

Эталон: other · ru

Результат: other; needs_human=True; status=error

Здравствуйте! Для этого обращения нужна проверка сотрудником. Опишите, что произошло, и при необходимости укажите сервер, ник и время события. Не отправляйте пароль или коды входа.

## Ограничения

- Synthetic data is a development check, not an organizer or production benchmark.
- Existing source IDs do not prove semantic support; grounding requires manual review.
- Latency measures processing, excludes CRM queue wait; costs are token-price estimates, not invoices.
- Offline results do not measure LLM quality; mixed model/prompt/corpus runs must be interpreted separately.
