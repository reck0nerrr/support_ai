import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Download, Plus, RefreshCw, X } from 'lucide-react';
import { api } from './api';
import { categories as crmCategories, contractCategories } from './types';
const categories = { ...crmCategories, ...contractCategories };

// Every displayed value comes from a persisted attempt or a server-computed evaluation.
type Runtime = {
  requests: number;
  attempts: number;
  ok: number;
  errors: number;
  needs_human_count: number;
  needs_human_rate: number | null;
  latency_p50_ms: number | null;
  latency_p95_ms: number | null;
  cost_per_request_usd: number | null;
  known_cost_usd: number;
  cost_coverage: number | null;
  priced_attempts: number;
  input_tokens: number;
  output_tokens: number;
  models: Record<string, number>;
  providers: Record<string, number>;
  cost_per_priced_success_usd: number | null;
  priced_successes: number;
  successful_latency_p95_ms: number | null;
};
type Metrics = {
  summary: Runtime;
  by_language: Record<string, Runtime>;
  categories: Record<string, number>;
  priorities?: Record<string, number>;
  duplicates_or_spam?: number;
  recent_runs: string[];
  days: number;
  truncated: boolean;
  generated_at: string;
  recent: {
    id: string;
    external_id: string | number | null;
    created_at: string;
    source: string;
    language: string;
    category: string;
    needs_human: boolean;
    status: string;
    latency_ms: number;
    cost_usd: number | null;
    error: string | null;
  }[];
};
type EvaluationItem = {
  id: string;
  name: string;
  dataset_kind: string;
  n: number;
  macro_f1: number | null;
  providers: Record<string, number>;
};
type Classification = {
  n: number;
  accuracy: number | null;
  macro_f1: number | null;
  confusion: Record<string, Record<string, number>>;
};
type Report = {
  name: string;
  dataset_kind: string;
  created_at: string;
  dataset_sha256: string;
  counts: {
    gold: number;
    predictions: number;
    missing: number;
    unexpected: number;
    reviewed: number;
  };
  classification: Classification;
  priority?: Classification;
  label_coverage?: { category: number; priority: number; language: number; needs_human: number };
  language_accuracy: number | null;
  runtime: Runtime;
  needs_human: {
    accuracy: number;
    precision: number | null;
    recall: number | null;
    false_negative: number;
    false_positive: number;
  };
  citations: {
    count: number;
    validity_rate: number | null;
    precision: number | null;
    recall: number | null;
    guardrail_rejections: number;
    human_supported_rate: number | null;
  };
  draft_quality: { reviewed: number; scores: Record<string, number | null> };
  by_language: Record<string, Classification & { language_accuracy: number | null; runtime: Runtime }>;
  examples: {
    id: string | number;
    expected: { category: string; language: string };
    prediction: {
      status: string;
      category: string;
      language: string;
      draft: string;
      needs_human: boolean;
      human_reasons: string[];
      error: string | null;
    } | null;
  }[];
};
const languages: Record<string, string> = {
  ru: 'Русский',
  kk: 'Қазақша',
  uz: 'O‘zbekcha',
  en: 'English',
  es: 'Español',
  pt: 'Português',
};
const percent = (v: number | null | undefined) =>
  v == null
    ? '—'
    : `${(v * 100).toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
const count = (v: number) => v.toLocaleString('ru-RU');
const money = (v: number | null) => (v === null ? '—' : `$${v.toFixed(6)}`);
const duration = (v: number | null) =>
  v === null ? '—' : `${(v / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} с`;
const kind = (value: string) =>
  ({
    synthetic: 'Синтетическая выборка',
    organizer: 'Данные организаторов',
    'real-reviewed': 'Размеченные реальные данные',
    unknown: 'Происхождение не указано',
  })[value] || value;
function Failure({ error, retry }: { error: string; retry?: () => void }) {
  return (
    <div className="error" role="alert">
      {error}
      {retry && <button onClick={retry}>Повторить</button>}
    </div>
  );
}
function RuntimeStrip({ value }: { value: Runtime }) {
  return (
    <dl className="metric-strip">
      <div>
        <dt>Обращений</dt>
        <dd>{count(value.requests)}</dd>
        <small>
          {count(value.attempts)} вызовов · {value.errors} ошибок
        </small>
      </div>
      <div>
        <dt>Нужен сотрудник</dt>
        <dd>{percent(value.needs_human_rate)}</dd>
        <small>
          {value.needs_human_count} из {value.requests}
        </small>
      </div>
      <div>
        <dt>p95 обработки</dt>
        <dd>{duration(value.latency_p95_ms)}</dd>
        <small>p50 {duration(value.latency_p50_ms)} · без ожидания в очереди</small>
      </div>
      <div>
        <dt>Стоимость / обращение</dt>
        <dd>{money(value.cost_per_request_usd)}</dd>
        <small>Покрытие тарифом и usage: {percent(value.cost_coverage)}</small>
        {value.cost_per_request_usd === null && value.priced_successes > 0 && (
          <small>
            Успешный вызов: {money(value.cost_per_priced_success_usd)} · n={value.priced_successes}
          </small>
        )}
      </div>
    </dl>
  );
}

export default function MetricsPage({ defaultProvider }: { defaultProvider: string }) {
  const [tab, setTab] = useState('runtime');
  return (
    <div className="standalone metrics-page">
      <div className="page-heading">
        <div>
          <h1>Качество и стоимость</h1>
          <p>Разборы Support Copilot: измерения сервиса и проверка на размеченных обращениях.</p>
        </div>
      </div>
      <div className="metrics-tabs" aria-label="Разделы метрик">
        <button aria-pressed={tab === 'runtime'} onClick={() => setTab('runtime')}>
          Работа сервиса
        </button>
        <button aria-pressed={tab === 'quality'} onClick={() => setTab('quality')}>
          Оценка качества
        </button>
      </div>
      {tab === 'runtime' ? <RuntimePage defaultProvider={defaultProvider} /> : <QualityPage />}
    </div>
  );
}

function RuntimePage({ defaultProvider }: { defaultProvider: string }) {
  const [provider, setProvider] = useState(defaultProvider === 'openai' ? 'openai' : 'offline');
  const [source, setSource] = useState('all'),
    [language, setLanguage] = useState('all'),
    [runId, setRunId] = useState('');
  const [data, setData] = useState<Metrics | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError('');
    api<Metrics>(`/metrics?${new URLSearchParams({ provider, source, language, run_id: runId })}`)
      .then((value) => {
        if (active) setData(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [provider, source, language, runId, refresh]);
  return (
    <>
      <div className="metrics-filters">
        <label>
          Провайдер
          <select
            value={provider}
            onChange={(e) => {
              setProvider(e.target.value);
              setRunId('');
            }}
          >
            <option value="openai">OpenAI</option>
            <option value="offline">Локальный режим</option>
          </select>
        </label>
        <label>
          Источник
          <select
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              setRunId('');
            }}
          >
            <option value="all">Все источники</option>
            <option value="http">HTTP /triage</option>
            <option value="batch">JSONL</option>
            <option value="crm">CRM и Telegram</option>
          </select>
        </label>
        <label>
          Язык
          <select
            value={language}
            onChange={(e) => {
              setLanguage(e.target.value);
              setRunId('');
            }}
          >
            <option value="all">Все языки</option>
            {Object.entries(languages).map(([code, text]) => (
              <option key={code} value={code}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <label className="run-filter">
          Запуск
          <select value={runId} onChange={(e) => setRunId(e.target.value)}>
            <option value="">Все за 7 дней</option>
            {data?.recent_runs.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
        </label>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => setRefresh((v) => v + 1)}
          aria-label="Обновить метрики"
        >
          <RefreshCw size={16} />
        </button>
      </div>
      {provider === 'offline' && (
        <p className="metrics-notice">
          Локальный режим выполняет эвристический разбор и резервный ответ. Его результаты проверяют запуск системы; они не
          измеряют качество LLM.
        </p>
      )}
      {error && <Failure error={error} retry={() => setRefresh((v) => v + 1)} />}
      {busy ? (
        <p className="metrics-loading" role="status">
          Считаем показатели…
        </p>
      ) : (
        data &&
        !error && (
          <>
            <RuntimeStrip value={data.summary} />
            {data.summary.requests === 0 && (
              <div className="metrics-empty">
                Для выбранных фильтров разборов пока нет. Вызовите POST /triage или обработайте
                обращение в CRM. Для сохранения JSONL-вызовов используйте make predict с PERSIST=1.
              </div>
            )}
            {data.truncated && (
              <p className="metrics-notice">
                Показаны последние 10 000 вызовов. Выберите отдельный запуск для точного сравнения.
              </p>
            )}
            <div className="metrics-grid">
              <section className="metrics-section">
                <h2>Языки обращений</h2>
                <div className="metrics-table-wrap">
                  <table className="metrics-table">
                    <thead>
                      <tr>
                        <th>Язык</th>
                        <th>Обращений</th>
                        <th>Человеку</th>
                        <th>Ошибки</th>
                        <th>p95</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(data.by_language).map(([lang, group]) => (
                        <tr key={lang}>
                          <th>{languages[lang] || lang}</th>
                          <td>{group.requests}</td>
                          <td>{percent(group.needs_human_rate)}</td>
                          <td>{group.errors}</td>
                          <td>{duration(group.latency_p95_ms)}</td>
                        </tr>
                      ))}
                      {!Object.keys(data.by_language).length && (
                        <tr>
                          <td colSpan={5} className="table-empty">
                            Показатели появятся после первого разбора.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <p className="metrics-caption">
                  Язык ответа; при сбое используется предварительное определение. Проверка по
                  эталону — в оценке качества.
                </p>
              </section>
              <section className="metrics-section">
                <h2>Классификация обращений</h2>
                <div className="category-bars">
                  {Object.entries(data.categories).map(([category, n]) => (
                    <div key={category}>
                      <span>{categories[category] || category}</span>
                      <strong>{n}</strong>
                      <progress
                        value={n}
                        max={Math.max(1, data.summary.ok)}
                        aria-label={categories[category] || category}
                      />
                    </div>
                  ))}
                  {!Object.keys(data.categories).length && (
                    <p className="table-empty">Успешных классификаций пока нет.</p>
                  )}
                </div>
                {data.priorities && (
                  <dl className="metric-key-values">
                    {Object.entries(data.priorities).map(([p, n]) => <div key={p}><dt>{p.toUpperCase()}</dt><dd>{n}</dd></div>)}
                    <div><dt>Спам или повтор</dt><dd>{data.duplicates_or_spam ?? 0}</dd></div>
                  </dl>
                )}
                <p className="metrics-caption">
                  Распределение ответов модели. Для accuracy и F1 нужна эталонная разметка.
                </p>
              </section>
            </div>
            <section className="metrics-section">
              <div className="metrics-section-heading">
                <h2>Последние вызовы</h2>
                <span>{new Date(data.generated_at).toLocaleTimeString('ru-RU')}</span>
              </div>
              <div className="metrics-table-wrap">
                <table className="metrics-table">
                  <thead>
                    <tr>
                      <th>Обращение · источник</th>
                      <th>Язык</th>
                      <th>Результат</th>
                      <th>Время</th>
                      <th>USD</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent.slice(0, 6).map((row) => (
                      <tr key={row.id}>
                        <th>
                          <span>{row.external_id ?? row.id.slice(0, 8)}</span>
                          <small>
                            {row.source} · {new Date(row.created_at).toLocaleString('ru-RU')}
                          </small>
                        </th>
                        <td>{row.language.toUpperCase()}</td>
                        <td className="metric-result">
                          {row.status === 'error' ? (
                            <span className="metric-negative">Ошибка · {row.error}</span>
                          ) : (
                            <>
                              {categories[row.category] || row.category}
                              <small>
                                {row.needs_human
                                  ? 'Нужен сотрудник'
                                  : 'Можно ответить автоматически'}
                              </small>
                            </>
                          )}
                        </td>
                        <td>{duration(row.latency_ms)}</td>
                        <td>{money(row.cost_usd)}</td>
                      </tr>
                    ))}
                    {!data.recent.length && (
                      <tr>
                        <td colSpan={5} className="table-empty">
                          Вызовов пока нет.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </section>
            <p className="metrics-caption">
              Токены: {count(data.summary.input_tokens)} входящих /{' '}
              {count(data.summary.output_tokens)} исходящих. Известная стоимость всех попыток:{' '}
              {money(data.summary.known_cost_usd)}. Повторные попытки входят в стоимость обращения.
              Неизвестная стоимость показана прочерком. Успешная обработка с известной стоимостью:{' '}
              {money(data.summary.cost_per_priced_success_usd)} (n={data.summary.priced_successes}).
            </p>
          </>
        )
      )}
    </>
  );
}

function QualityPage() {
  const [items, setItems] = useState<EvaluationItem[]>([]),
    [selected, setSelected] = useState('');
  const [report, setReport] = useState<Report | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(true),
    [showUpload, setShowUpload] = useState(false),
    [allExamples, setAllExamples] = useState(false),
    [allLanguages, setAllLanguages] = useState(false);
  const load = useCallback(async (id?: string) => {
    setError('');
    setBusy(true);
    try {
      const list = await api<EvaluationItem[]>('/evaluations');
      setItems(list);
      setSelected(id || list[0]?.id || '');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    if (!selected) {
      setReport(null);
      return;
    }
    let active = true;
    setBusy(true);
    setError('');
    setAllExamples(false);
    api<Report>(`/evaluations/${selected}`)
      .then((value) => {
        if (active) setReport(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [selected]);
  const download = () => {
    if (!report) return;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = `evaluation-${selected}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };
  return (
    <>
      <div className="quality-toolbar">
        <label>
          Оценочный запуск
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            <option value="" disabled>
              Выберите оценку
            </option>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} · {item.n} обращений
              </option>
            ))}
          </select>
        </label>
        <button className="primary" onClick={() => setShowUpload(true)}>
          <Plus size={16} />
          Добавить оценку
        </button>
        {report && (
          <button className="secondary" onClick={download}>
            <Download size={16} />
            JSON отчёта
          </button>
        )}
      </div>
      {error && <Failure error={error} retry={() => void load(selected)} />}
      {busy ? (
        <p role="status" className="metrics-loading">
          Загружаем оценку…
        </p>
      ) : !report ? (
        <div className="metrics-empty">
          <h2>Сначала сравним с эталоном</h2>
          <p>
            Загрузите отдельные файлы разметки и предсказаний. Сервер рассчитает метрики; значения
            качества появятся после оценки.
          </p>
          <code>make predict IN=datasets/dev.tickets.jsonl OUT=pred.jsonl</code>
          <p>
            Готовый пример разметки: datasets/contract.gold.jsonl. Это синтетические данные для
            разработки.
          </p>
        </div>
      ) : (
        !error && (
          <>
            <div className="evaluation-identity">
              <strong>{report.name}</strong>
              <span>
                {kind(report.dataset_kind)} · {report.counts.gold} обращений
              </span>
              <span>
                {Object.keys(report.runtime.providers).join(', ')} ·{' '}
                {Object.keys(report.runtime.models).join(', ')} · {report.runtime.ok} из{' '}
                {report.counts.gold} успешно · {report.runtime.errors} ошибок
              </span>
            </div>
            {(report.dataset_kind === 'synthetic' ||
              Object.keys(report.runtime.providers).includes('offline')) && (
              <p className="metrics-notice">
                {report.dataset_kind === 'synthetic'
                  ? 'Синтетический набор проверяет сценарии разработки. '
                  : ''}
                {Object.keys(report.runtime.providers).includes('offline')
                  ? 'Использован локальный резервный разбор; это не оценка черновиков LLM.'
                  : 'Результат не заменяет проверку на независимых данных организаторов.'}
              </p>
            )}
            {report.label_coverage && (!report.label_coverage.category || !report.label_coverage.priority) && (
              <p className="metrics-notice">В выборке нет полной ручной разметки категорий и приоритетов. Отсутствующие оценки показаны прочерком; ответы администраторов в разбор не передаются.</p>
            )}
            <dl className="metric-strip quality-strip">
              <div>
                <dt>Accuracy категории</dt>
                <dd>{percent(report.classification.accuracy)}</dd>
                <small>{report.classification.n} размеченных обращений</small>
              </div>
              <div>
                <dt>Macro-F1 приоритета</dt>
                <dd>{percent(report.priority?.macro_f1)}</dd>
                <small>{report.priority?.n || 0} меток p0–p3</small>
              </div>
              <div>
                <dt>Валидные ссылки</dt>
                <dd>{percent(report.citations.validity_rate)}</dd>
                <small>{report.citations.count} ссылок · проверка пункта и редакции</small>
              </div>
              <div>
                <dt>Качество черновика</dt>
                <dd>
                  {report.draft_quality.reviewed
                    ? `${(Object.values(report.draft_quality.scores).reduce<number>((a, b) => a + (b || 0), 0) / 4).toFixed(1)} / 5`
                    : '—'}
                </dd>
                <small>
                  {report.draft_quality.reviewed
                    ? `${report.draft_quality.reviewed} ручных оценок`
                    : 'Ожидает ручной оценки'}
                </small>
              </div>
            </dl>
            <div className="metrics-grid">
              <section className="metrics-section">
                <div className="metrics-section-heading">
                  <h2>Качество по языкам</h2>
                  {Object.keys(report.by_language).length > 3 && <button className="text-button" onClick={() => setAllLanguages(v => !v)}>{allLanguages ? 'Свернуть' : `Все языки (${Object.keys(report.by_language).length})`}</button>}
                </div>
                {report.label_coverage?.language === 0 && <p className="metrics-caption">Группы — по языковой подсказке экспорта. Качество языка ожидает ручной разметки и оценки носителями.</p>}
                <div className="metrics-table-wrap">
                  <table className="metrics-table">
                    <thead>
                      <tr>
                        <th>Язык</th>
                        <th>N</th>
                        <th>Accuracy</th>
                        <th>Macro-F1</th>
                        <th>Язык ответа</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(report.by_language).sort(([a], [b]) => ['kk','uz','ru','en','es','pt','und'].indexOf(a) - ['kk','uz','ru','en','es','pt','und'].indexOf(b)).slice(0, allLanguages ? undefined : 3).map(([lang, group]) => (
                        <tr key={lang}>
                          <th>{languages[lang] || lang}</th>
                          <td>{group.n}</td>
                          <td>{percent(group.accuracy)}</td>
                          <td>{percent(group.macro_f1)}</td>
                          <td>{percent(group.language_accuracy)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className="metrics-section">
                <h2>Когда нужен человек</h2>
                <dl className="metric-key-values">
                  <div>
                    <dt>Доля needs_human</dt>
                    <dd>{percent(report.runtime.needs_human_rate)}</dd>
                  </div>
                  <div>
                    <dt>Recall / precision</dt>
                    <dd>
                      {percent(report.needs_human.recall)} / {percent(report.needs_human.precision)}
                    </dd>
                  </div>
                  <div>
                    <dt>Пропущено сложных случаев по разметке</dt>
                    <dd className={report.needs_human.false_negative ? 'metric-negative' : ''}>
                      {report.label_coverage?.needs_human === 0 ? '—' : report.needs_human.false_negative}
                    </dd>
                  </div>
                  <div>
                    <dt>Излишних передач сотруднику</dt>
                    <dd>{report.label_coverage?.needs_human === 0 ? '—' : report.needs_human.false_positive}</dd>
                  </div>
                </dl>
              </section>
            </div>
            <div className="metrics-grid">
              <section className="metrics-section">
                <h2>Правила и черновики</h2>
                <dl className="metric-key-values">
                  <div>
                    <dt>Precision / recall ссылок по эталону</dt>
                    <dd>
                      {percent(report.citations.precision)} / {percent(report.citations.recall)}
                    </dd>
                  </div>
                  <div>
                    <dt>Отклонено проверкой ссылок</dt>
                    <dd>{report.citations.guardrail_rejections}</dd>
                  </div>
                  <div>
                    <dt>Подтверждено ручной проверкой</dt>
                    <dd>{percent(report.citations.human_supported_rate)}</dd>
                  </div>
                </dl>
                <p className="metrics-caption">
                  Существующая ссылка может не подтверждать текст. Смысловую корректность проверяет
                  человек.
                </p>
              </section>
              <section className="metrics-section">
                <h2>Стоимость и задержка</h2>
                <p className="metrics-caption">Цели задания: ≤ $0,002 на обращение и p95 ≤ 5 секунд.</p>
                <dl className="metric-key-values">
                  <div>
                    <dt>p50 / p95 обработки</dt>
                    <dd>
                      {duration(report.runtime.latency_p50_ms)} /{' '}
                      {duration(report.runtime.latency_p95_ms)}
                    </dd>
                  </div>
                  <div>
                    <dt>p95 успешного разбора</dt>
                    <dd className={(report.runtime.successful_latency_p95_ms || 0) > 5000 ? 'metric-negative' : ''}>{duration(report.runtime.successful_latency_p95_ms)}</dd>
                  </div>
                  <div>
                    <dt>На обращение, USD</dt>
                    <dd>{money(report.runtime.cost_per_request_usd)}</dd>
                  </div>
                  <div>
                    <dt>Успешная обработка с расчётом, USD</dt>
                    <dd>
                      {money(report.runtime.cost_per_priced_success_usd)} · n=
                      {report.runtime.priced_successes}
                    </dd>
                  </div>
                  <div>
                    <dt>Покрытие расчётом стоимости</dt>
                    <dd>{percent(report.runtime.cost_coverage)}</dd>
                  </div>
                  <div>
                    <dt>Ошибок / пропущено строк</dt>
                    <dd>
                      {report.runtime.errors} / {report.counts.missing}
                    </dd>
                  </div>
                </dl>
              </section>
            </div>
            <section className="metrics-section">
              <div className="metrics-section-heading">
                <h2>Примеры черновиков</h2>
                {report.examples.length > 3 && (
                  <button className="text-button" onClick={() => setAllExamples((v) => !v)}>
                    {allExamples ? 'Свернуть' : `Все ${report.examples.length}`}
                  </button>
                )}
              </div>
              <div className="draft-examples">
                {report.examples.slice(0, allExamples ? undefined : 3).map((example) => (
                  <article key={example.id}>
                    <div>
                      <strong>{String(example.id)}</strong>
                      <span>
                        {report.label_coverage?.language === 0 ? 'Подсказка языка: ' : ''}{example.expected.language.toUpperCase()} · {example.expected.category ? 'эталон: ' : ''}
                        {categories[example.expected.category] || example.expected.category || 'не размечено'}
                      </span>
                    </div>
                    {example.prediction ? (
                      <>
                        <p className="draft-meta">
                          {categories[example.prediction.category]} ·{' '}
                          {example.prediction.needs_human
                            ? 'нужен сотрудник'
                            : 'самостоятельный ответ'}
                          {example.prediction.error && ` · ${example.prediction.error}`}
                        </p>
                        <p className="example-draft" lang={example.prediction.language}>
                          {example.prediction.draft}
                        </p>
                      </>
                    ) : (
                      <p>Предсказание отсутствует.</p>
                    )}
                  </article>
                ))}
              </div>
            </section>
            <details className="metrics-section">
              <summary>Матрица ошибок классификации</summary>
              <div className="metrics-table-wrap">
                <table className="metrics-table">
                  <thead>
                    <tr>
                      <th>Эталон → результат</th>
                      {Object.keys(categories).map((c) => (
                        <th key={c}>{c}</th>
                      ))}
                      <th>Ошибка</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(report.classification.confusion).map(([actual, guesses]) => (
                      <tr key={actual}>
                        <th>{categories[actual] || actual}</th>
                        {Object.keys(categories).map((c) => (
                          <td key={c}>{guesses[c] || 0}</td>
                        ))}
                        <td>{guesses.__error__ || 0}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
            <p className="metrics-caption">
              Эталон SHA-256: <code>{report.dataset_sha256.slice(0, 16)}</code>. Дата расчёта:{' '}
              {new Date(report.created_at).toLocaleString('ru-RU')}. Все показатели рассчитаны
              сервером из загруженных строк.
            </p>
          </>
        )
      )}
      {showUpload && (
        <EvaluationUpload
          onClose={() => setShowUpload(false)}
          onCreated={(id) => {
            setShowUpload(false);
            void load(id);
          }}
        />
      )}
    </>
  );
}

function EvaluationUpload({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => before?.focus();
  }, []);
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    const form = new FormData(event.currentTarget);
    const parse = async (name: string, optional = false) => {
      const file = form.get(name) as File;
      if (!file?.size && optional) return [];
      if (!file?.size) throw new Error('Выберите входной набор и предсказания.');
      if (file.size > 8_000_000)
        throw new Error(
          'Для загрузки через админку файл должен быть меньше 8 МБ. Большие наборы оцените через CLI с --persist.',
        );
      return (await file.text())
        .replace(/^\uFEFF/, '')
        .trim()
        .split(/\r?\n/)
        .map((line, i) => {
          try {
            return JSON.parse(line);
          } catch {
            throw new Error(`Некорректный JSON в файле ${file.name}, строка ${i + 1}`);
          }
        });
    };
    try {
      const result = await api<{ id: string }>('/evaluations', {
        method: 'POST',
        body: JSON.stringify({
          name: form.get('name'),
          dataset_kind: form.get('kind'),
          gold: await parse('gold'),
          predictions: await parse('pred'),
          reviews: await parse('reviews', true),
        }),
      });
      onCreated(result.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <dialog
      ref={dialog}
      className="evaluation-dialog modal"
      aria-labelledby="evaluation-title"
      onCancel={onClose}
    >
      <header>
        <h2 id="evaluation-title">Оценить предсказания</h2>
        <button className="icon-button" onClick={onClose} aria-label="Закрыть оценку">
          <X size={20} />
        </button>
      </header>
      <p>
        Рассчитаем показатели по готовым предсказаниям. Входной набор может быть без разметки — Accuracy и F1 появятся после её добавления. Вызовов модели и расходов на API не
        будет.
      </p>
      <form onSubmit={submit}>
        <label>
          Название запуска
          <input name="name" defaultValue="Проверка RU · KK · UZ" maxLength={200} required />
        </label>
        <label>
          Происхождение данных
          <select name="kind" defaultValue="synthetic">
            <option value="synthetic">Синтетические</option>
            <option value="organizer">От организаторов</option>
            <option value="real-reviewed">Реальные, размеченные человеком</option>
            <option value="unknown">Не указано</option>
          </select>
        </label>
        <label>
          Эталонная разметка · .jsonl
          <input name="gold" type="file" accept=".jsonl,.ndjson" required />
        </label>
        <label>
          Предсказания · .jsonl
          <input name="pred" type="file" accept=".jsonl,.ndjson" required />
        </label>
        <label>
          Ручная оценка черновиков · необязательно
          <input name="reviews" type="file" accept=".jsonl,.ndjson" />
        </label>
        {error && <Failure error={error} />}
        <button className="primary" disabled={busy}>
          {busy ? 'Считаем…' : 'Рассчитать и сохранить'}
        </button>
      </form>
    </dialog>
  );
}
