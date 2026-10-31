import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  ArrowLeft,
  ArrowUpRight,
  BookOpen,
  BarChart3,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleHelp,
  FileText,
  Inbox,
  LogOut,
  Menu,
  MessageSquare,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  UserRound,
  X,
} from 'lucide-react';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import './styles.css';
import { api, setCsrf } from './api';
import { Auth, Rule, Staff, System, Ticket, categories, contractCategories, aiErrors, delivery, statuses } from './types';
import MetricsPage from './MetricsPage';

const date = (value: string) =>
  new Date(
    value.endsWith('Z') || /[+-]\d\d:\d\d$/.test(value) ? value : value + 'Z',
  ).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
const shortDate = (value: string) => date(value).replace(/, /, ' · ');
function Mark() {
  return (
    <svg viewBox="0 0 32 32" width="32" height="32" fill="none" aria-hidden="true">
      <path d="M27 10A12 12 0 1 0 28 21H17v-6h13" stroke="currentColor" strokeWidth="4" />
      <path d="m10 27 3-8 4 5 3-5 4 8" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
function Brand() {
  return (
    <div className="brand">
      <Mark />
      <div>
        <strong>Support Copilot</strong>
        <span>Grand Mobile</span>
      </div>
    </div>
  );
}
function ErrorBox({ text, retry }: { text: string; retry?: () => void }) {
  return (
    <div className="error" role="alert">
      {text}
      {retry && <button onClick={retry}>Повторить</button>}
    </div>
  );
}
function Badge({ value }: { value: string }) {
  return <span className={`badge status-${value}`}>{statuses[value] || value}</span>;
}

function Login({ onLogin }: { onLogin: (auth: Auth) => void }) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    const values = new FormData(event.currentTarget);
    try {
      onLogin(
        await api<Auth>('/auth/login', {
          method: 'POST',
          body: JSON.stringify(Object.fromEntries(values)),
        }),
      );
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="login-page">
      <div className="login-side">
        <Brand />
        <div className="login-statement">
          <h2>
            У каждой жалобы
            <br />
            есть своя история.
          </h2>
          <p>Факты, правила и переписка — в одном рабочем пространстве поддержки.</p>
          <div className="login-flow">
            <span>Обращение</span>
            <ArrowUpRight />
            <span>Разбор</span>
            <ArrowUpRight />
            <span>Решение</span>
          </div>
        </div>
        <p className="login-footer">Служба поддержки Grand Mobile</p>
      </div>
      <div className="login-main">
        <form onSubmit={submit} className="login-form">
          <ShieldCheck size={24} />
          <h1>Вход в поддержку</h1>
          <p>Рабочее пространство сотрудников проекта.</p>
          <label>
            Логин
            <input name="login" autoComplete="username" required maxLength={100} autoFocus />
          </label>
          <label>
            Пароль
            <input
              name="password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={200}
            />
          </label>
          {error && <ErrorBox text={error} />}
          <button className="primary" disabled={busy}>
            {busy ? 'Входим…' : 'Войти в рабочее пространство'}
            <ArrowUpRight size={16} />
          </button>
          <p className="muted">Нет доступа? Обратитесь к администратору поддержки.</p>
        </form>
      </div>
    </main>
  );
}

function App() {
  const [auth, setAuth] = useState<Auth | null>(null),
    [starting, setStarting] = useState(true),
    [startError, setStartError] = useState('');
  const [system, setSystem] = useState<System | null>(null),
    [staff, setStaff] = useState<Staff[]>([]);
  const [view, setView] = useState('all'),
    [menu, setMenu] = useState(false),
    [selected, setSelected] = useState<number | null>(null),
    [showDemo, setShowDemo] = useState(false),
    [logoutError, setLogoutError] = useState('');
  const acceptAuth = (value: Auth) => {
    setCsrf(value.csrf);
    setAuth(value);
  };
  const boot = useCallback(async () => {
    setStartError('');
    setStarting(true);
    try {
      acceptAuth(await api<Auth>('/auth/me'));
    } catch (error) {
      if (!(error as Error).message.includes('Войдите')) setStartError((error as Error).message);
    } finally {
      setStarting(false);
    }
  }, []);
  useEffect(() => {
    void boot();
    const expired = () => {
      setAuth(null);
      setCsrf('');
    };
    window.addEventListener('session-expired', expired);
    return () => window.removeEventListener('session-expired', expired);
  }, [boot]);
  useEffect(() => {
    if (auth) {
      api<System>('/system')
        .then(setSystem)
        .catch((error) => setLogoutError(error.message));
      api<Staff[]>('/staff')
        .then(setStaff)
        .catch((error) => setLogoutError(error.message));
    }
  }, [auth]);
  const logout = async () => {
    try {
      await api('/auth/logout', { method: 'POST' });
      setAuth(null);
      setCsrf('');
      setSelected(null);
    } catch (error) {
      setLogoutError((error as Error).message);
    }
  };
  if (starting)
    return (
      <div className="boot">
        <Brand />
        <p role="status">Открываем рабочее пространство…</p>
      </div>
    );
  if (startError && !auth)
    return (
      <div className="boot">
        <Brand />
        <ErrorBox text={startError} retry={boot} />
      </div>
    );
  if (!auth) return <Login onLogin={acceptAuth} />;
  const nav = [
    { id: 'all', text: 'Все обращения', icon: Inbox },
    { id: 'mine', text: 'Назначены мне', icon: UserRound },
    { id: 'needs_info', text: 'Ждём игрока', icon: MessageSquare },
    { id: 'resolved', text: 'Решённые', icon: Check },
  ];
  const navigate = (id: string) => {
    setView(id);
    setSelected(null);
    setMenu(false);
  };
  return (
    <div className="app-shell">
      <aside className={`sidebar ${menu ? 'open' : ''}`}>
        <Brand />
        <button
          className="mobile-close icon-button"
          onClick={() => setMenu(false)}
          aria-label="Закрыть меню"
        >
          <X size={20} />
        </button>
        <div className="workspace">
          <span className="workspace-mark">GM</span>
          <div>
            <strong>Поддержка проекта</strong>
            <span>
              {auth.staff.role === 'admin'
                ? 'Все серверы'
                : auth.staff.servers.join(', ') || 'Серверы не назначены'}
            </span>
          </div>
        </div>
        <nav aria-label="Рабочие разделы">
          <p className="nav-label">Рабочая очередь</p>
          {nav.map((n) => (
            <button
              key={n.id}
              className={view === n.id ? 'active' : ''}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={17} />
              {n.text}
            </button>
          ))}
          <p className="nav-label second">Материалы и настройки</p>
          {auth.staff.role === 'admin' && (
            <button
              className={view === 'metrics' ? 'active' : ''}
              onClick={() => navigate('metrics')}
            >
              <BarChart3 size={17} />
              Качество и стоимость
            </button>
          )}
          <button className={view === 'rules' ? 'active' : ''} onClick={() => navigate('rules')}>
            <BookOpen size={17} />
            База правил
          </button>
          <button className={view === 'system' ? 'active' : ''} onClick={() => navigate('system')}>
            <Settings size={17} />
            Подключения
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="staff-row">
            <span className="avatar">{auth.staff.name[0]}</span>
            <div>
              <strong>{auth.staff.name}</strong>
              <span>
                {{
                  admin: 'Администратор',
                  senior: 'Старший модератор',
                  operator: 'Оператор',
                }[auth.staff.role] || auth.staff.role}
              </span>
            </div>
            <button className="icon-button" aria-label="Выйти" onClick={logout}>
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <button
            className="menu-button icon-button"
            onClick={() => setMenu(true)}
            aria-label="Открыть меню"
          >
            <Menu size={20} />
          </button>
          <div className="breadcrumb">
            Grand Mobile <span>/</span> Поддержка
          </div>
          <div className="topbar-right">
            <span className="online-dot" />
            Рабочее пространство
          </div>
        </header>
        <main className="sheet">
          {logoutError && <ErrorBox text={logoutError} retry={() => setLogoutError('')} />}{' '}
          {view === 'metrics' ? (
            <MetricsPage defaultProvider={system?.ai_provider || 'offline'} />
          ) : view === 'rules' ? (
            <RulesPage admin={auth.staff.role === 'admin'} />
          ) : view === 'system' ? (
            <SystemPage system={system} />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <h1>{nav.find((n) => n.id === view)?.text}</h1>
                  <p>Обращения игроков и решения вашей команды.</p>
                </div>
                {system?.demo_enabled && auth.staff.role === 'admin' && (
                  <button className="secondary" onClick={() => setShowDemo(true)}>
                    <Plus size={16} />
                    Тестовое обращение
                  </button>
                )}
              </div>
              <InboxPage
                key={view}
                view={view}
                selected={selected}
                onSelect={setSelected}
                staff={staff}
                me={auth.staff}
                system={system}
              />
            </>
          )}
        </main>
      </div>
      {showDemo && (
        <DemoModal
          onClose={() => setShowDemo(false)}
          onCreated={(ticket) => {
            setShowDemo(false);
            setView('all');
            setSelected(ticket.id);
          }}
        />
      )}
    </div>
  );
}

function InboxPage({
  view,
  selected,
  onSelect,
  staff,
  me,
  system,
}: {
  view: string;
  selected: number | null;
  onSelect: (id: number | null) => void;
  staff: Staff[];
  me: Staff;
  system: System | null;
}) {
  const [items, setItems] = useState<Ticket[]>([]),
    [total, setTotal] = useState(0),
    [q, setQ] = useState(''),
    [query, setQuery] = useState('');
  const [status, setStatus] = useState(''),
    [category, setCategory] = useState(''),
    [server, setServer] = useState(''),
    [page, setPage] = useState(1),
    [busy, setBusy] = useState(true),
    [error, setError] = useState(''),
    [detailTick, setDetailTick] = useState(0);
  const request = useRef(0);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(q);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [q]);
  const load = useCallback(async () => {
    const id = ++request.current;
    try {
      const params = new URLSearchParams({
        q: query,
        status: view === 'needs_info' || view === 'resolved' ? view : status,
        category,
        server,
        mine: String(view === 'mine'),
        page: String(page),
      });
      const result = await api<{ items: Ticket[]; total: number }>(`/tickets?${params}`);
      if (id === request.current) {
        setItems(result.items);
        setTotal(result.total);
        setError('');
      }
    } catch (error) {
      if (id === request.current) setError((error as Error).message);
    } finally {
      if (id === request.current) setBusy(false);
    }
  }, [query, status, category, server, page, view]);
  useEffect(() => {
    setBusy(true);
    void load();
    const timer = window.setInterval(load, 7000);
    return () => {
      clearInterval(timer);
      request.current++;
    };
  }, [load]);
  const changeFilter = (setter: (value: string) => void, value: string) => {
    setter(value);
    setPage(1);
  };
  return (
    <div className={`inbox-layout ${selected ? 'has-selection' : ''}`}>
      <section className="queue" aria-label="Очередь обращений">
        <div className="queue-controls">
          <div className="queue-title">
            <h2>
              Очередь <span>{total}</span>
            </h2>
            <button
              className="icon-button"
              onClick={() => {
                void load();
                setDetailTick((v) => v + 1);
              }}
              aria-label="Обновить обращения"
            >
              <RefreshCw size={16} />
            </button>
          </div>
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Поиск обращений"
              placeholder="Номер, ник или тема"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </label>
          <div className="filters">
            <select
              aria-label="Статус"
              value={status}
              onChange={(e) => changeFilter(setStatus, e.target.value)}
              disabled={view === 'needs_info' || view === 'resolved'}
            >
              <option value="">Все статусы</option>
              {Object.entries(statuses).map(([key, label]) => (
                <option value={key} key={key}>
                  {label}
                </option>
              ))}
            </select>
            <select
              aria-label="Категория"
              value={category}
              onChange={(e) => changeFilter(setCategory, e.target.value)}
            >
              <option value="">Все категории</option>
              {Object.entries(categories).map(([key, label]) => (
                <option value={key} key={key}>
                  {label}
                </option>
              ))}
            </select>
            <select
              aria-label="Сервер"
              value={server}
              onChange={(e) => changeFilter(setServer, e.target.value)}
            >
              <option value="">Все серверы</option>
              {system?.servers.map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </div>
        </div>
        {error && <ErrorBox text={error} retry={load} />}
        <div className="ticket-list" aria-busy={busy}>
          {busy && !items.length ? (
            <div className="empty" role="status">
              Загружаем обращения…
            </div>
          ) : !items.length ? (
            <div className="empty">
              <Inbox size={25} />
              <h3>
                {query || status || category || server ? 'Ничего не найдено' : 'Очередь свободна'}
              </h3>
              <p>
                {query || status || category || server
                  ? 'Попробуйте изменить условия поиска.'
                  : 'Новые обращения из Telegram появятся здесь.'}
              </p>
            </div>
          ) : (
            items.map((t) => (
              <button
                key={t.id}
                className={`ticket-row ${selected === t.id ? 'selected' : ''}`}
                onClick={() => onSelect(t.id)}
              >
                <div className="ticket-meta">
                  <span>
                    #{t.id}
                    {t.demo ? ' · демо' : ''}
                  </span>
                  <time>{shortDate(t.updated_at)}</time>
                </div>
                <div className="ticket-identity">
                  <strong>{t.profile?.nickname || t.player.name}</strong>
                  {t.priority === 'high' && (
                    <span className="priority-mark" title="Высокий приоритет" />
                  )}
                </div>
                <p className="ticket-subject">{t.title}</p>
                <div className="ticket-row-footer">
                  <span>{t.profile?.server || 'Без персонажа'}</span>
                  <Badge value={t.status} />
                </div>
              </button>
            ))
          )}
        </div>
        {total > 30 && (
          <div className="pagination">
            <button
              className="icon-button"
              aria-label="Предыдущая страница"
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
            >
              <ChevronLeft size={16} />
            </button>
            <span>
              {(page - 1) * 30 + 1}–{Math.min(page * 30, total)} из {total}
            </span>
            <button
              className="icon-button"
              aria-label="Следующая страница"
              disabled={page * 30 >= total}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        )}
      </section>
      {selected ? (
        <TicketDetail
          key={selected}
          id={selected}
          refreshTick={detailTick}
          staff={staff}
          me={me}
          onBack={() => onSelect(null)}
          onChanged={load}
        />
      ) : (
        <section className="no-selection">
          <div className="case-file">
            <FileText size={32} />
            <h2>Начните с обращения</h2>
            <p>
              Выберите жалобу в очереди, чтобы проверить факты, посмотреть материалы и подготовить
              ответ.
            </p>
            <div className="case-steps">
              <span>Переписка</span>
              <span>Источники</span>
              <span>Черновик</span>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}

function TicketDetail({
  id,
  refreshTick,
  staff,
  me,
  onBack,
  onChanged,
}: {
  id: number;
  refreshTick: number;
  staff: Staff[];
  me: Staff;
  onBack: () => void;
  onChanged: () => void;
}) {
  const [ticket, setTicket] = useState<Ticket | null>(null),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [tab, setTab] = useState('conversation');
  const [text, setText] = useState(''),
    [internal, setInternal] = useState(false),
    [aiTab, setAiTab] = useState('analysis');
  const requestKey = useRef(crypto.randomUUID());
  const [composerRevision, setComposerRevision] = useState<number | null>(null);
  const mounted = useRef(true);
  const load = useCallback(async () => {
    try {
      const t = await api<Ticket>(`/tickets/${id}`);
      if (mounted.current) {
        setTicket(t);
        setError('');
      }
    } catch (error) {
      if (mounted.current) setError((error as Error).message);
    }
  }, [id]);
  useEffect(() => {
    mounted.current = true;
    void load();
    const timer = window.setInterval(load, 7000);
    return () => {
      mounted.current = false;
      clearInterval(timer);
    };
  }, [load]);
  useEffect(() => {
    void load();
  }, [refreshTick, load]);
  const act = async (path: string, method: string, body?: unknown) => {
    setBusy(true);
    setError('');
    try {
      const value = await api<Ticket>(path, {
        method,
        body: body ? JSON.stringify(body) : undefined,
      });
      setTicket(value);
      onChanged();
      return true;
    } catch (error) {
      setError((error as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  };
  if (!ticket)
    return (
      <section className="detail-loading">
        {error ? <ErrorBox text={error} retry={load} /> : <p role="status">Открываем обращение…</p>}
      </section>
    );
  const patch = (fields: object) =>
    act(`/tickets/${id}`, 'PATCH', { ...fields, revision: ticket.revision });
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    if (
      await act(`/tickets/${id}/messages`, 'POST', {
        text,
        internal,
        revision: composerRevision ?? ticket.revision,
        request_key: requestKey.current,
      })
    ) {
      setText('');
      setComposerRevision(null);
      requestKey.current = crypto.randomUUID();
    }
  };
  const analysis = ticket.analysis;
  const usableDraft = analysis && !analysis.stale;
  return (
    <section className="ticket-detail">
      <header className="detail-header">
        <div className="detail-heading">
          <button className="back-button icon-button" onClick={onBack} aria-label="К очереди">
            <ArrowLeft size={18} />
          </button>
          <div>
            <div className="detail-id">
              <span>Обращение #{id}</span>
              <Badge value={ticket.status} />
              {ticket.demo && <span className="badge">Демо</span>}
            </div>
            <h2>{categories[ticket.category]}</h2>
          </div>
        </div>
        <button
          className="secondary claim-button"
          disabled={busy || ticket.assignee?.id === me.id}
          onClick={() => patch({ assignee_id: me.id })}
        >
          <UserRound size={15} />
          {ticket.assignee?.id === me.id ? 'Назначено вам' : 'Взять в работу'}
        </button>
      </header>
      <div className="detail-columns">
        <div className="conversation-column">
          <section className="player-strip">
            <span className="avatar player-avatar">
              {(ticket.profile?.nickname || ticket.player.name)[0]}
            </span>
            <div>
              <strong>{ticket.profile?.nickname || ticket.player.name}</strong>
              <p>
                {ticket.profile?.server || 'Персонаж не указан'} <span>·</span>{' '}
                {ticket.player.language.toUpperCase()} <span>·</span> Telegram
              </p>
            </div>
            <span className={`verification ${ticket.profile?.verified ? 'verified' : ''}`}>
              <ShieldCheck size={14} />
              {ticket.profile?.verified ? 'Подтверждён' : 'Не подтверждён'}
            </span>
          </section>
          <div className="tabs">
            <button
              className={tab === 'conversation' ? 'active' : ''}
              onClick={() => setTab('conversation')}
            >
              Переписка
            </button>
            <button className={tab === 'history' ? 'active' : ''} onClick={() => setTab('history')}>
              История действий
            </button>
            <span>{date(ticket.created_at)}</span>
          </div>
          {error && <ErrorBox text={error} retry={load} />}
          <div className="conversation-content">
            {tab === 'history' ? (
              <div className="audit-list">
                {ticket.audit?.map((a, i) => (
                  <div key={i}>
                    <strong>{a.action}</strong>
                    <p>
                      {a.actor} <span>·</span> {date(a.created_at)}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <>
                {ticket.parent_id && (
                  <p className="relation">Апелляция по обращению #{ticket.parent_id}</p>
                )}
                {ticket.messages?.map((m) => (
                  <article key={m.id} className={`message message-${m.author}`}>
                    <header>
                      <strong>
                        {m.author === 'player'
                          ? ticket.profile?.nickname || ticket.player.name
                          : m.author === 'assistant'
                            ? 'Support Copilot · автоответ'
                            : m.author === 'note'
                              ? 'Внутренний комментарий'
                              : 'Поддержка'}
                      </strong>
                      <time>{date(m.created_at)}</time>
                    </header>
                    <p>{m.text}</p>
                    {m.delivery && (
                      <div className={`delivery delivery-${m.delivery}`}>
                        {delivery[m.delivery]}
                        {m.delivery === 'failed' && (
                          <button
                            onClick={() => act(`/tickets/${id}/messages/${m.id}/retry`, 'POST')}
                            disabled={busy}
                          >
                            Повторить отправку
                          </button>
                        )}
                      </div>
                    )}
                  </article>
                ))}
                <section className="evidence">
                  <h3>
                    <Paperclip size={15} />
                    Доказательства <span>{ticket.attachments?.length || 0}</span>
                  </h3>
                  {ticket.attachments?.length ? (
                    ticket.attachments.map((a) => (
                      <a
                        key={a.id}
                        href={`/api/attachments/${a.id}`}
                        className="attachment"
                        target="_blank"
                        rel="noreferrer"
                      >
                        <FileText size={18} />
                        <span>
                          {a.name}
                          <small>
                            {a.size ? `${(a.size / 1024 / 1024).toFixed(1)} МБ` : a.mime}
                          </small>
                        </span>
                        <ArrowUpRight size={15} />
                      </a>
                    ))
                  ) : (
                    <p>Файлы не приложены. Ссылки могут быть в сообщении игрока.</p>
                  )}
                </section>
              </>
            )}
          </div>
          <form className={`composer ${internal ? 'internal' : ''}`} onSubmit={send}>
            <div className="composer-heading">
              <label>
                <input
                  type="checkbox"
                  checked={internal}
                  onChange={(e) => {
                    setInternal(e.target.checked);
                    requestKey.current = crypto.randomUUID();
                  }}
                />
                Внутренний комментарий
              </label>
              <span>
                {internal ? 'Виден команде' : ticket.demo ? 'Демо-ответ' : 'Ответ игроку'}
              </span>
            </div>
            {composerRevision !== null && composerRevision !== ticket.revision && (
              <div className="composer-conflict" role="status">
                Обращение изменилось во время подготовки ответа. Проверьте переписку.
                <button type="button" onClick={() => setComposerRevision(ticket.revision)}>
                  Проверил изменения
                </button>
              </div>
            )}
            <textarea
              aria-label={internal ? 'Внутренний комментарий' : 'Ответ игроку'}
              placeholder={
                internal
                  ? 'Что нужно знать команде?'
                  : 'Напишите ответ или используйте черновик AI…'
              }
              maxLength={3500}
              value={text}
              onChange={(e) => {
                setText(e.target.value);
                setComposerRevision((previous) => previous ?? ticket.revision);
                requestKey.current = crypto.randomUUID();
              }}
              required
              rows={4}
            />
            <div className="composer-footer">
              <span>{text.length} / 3 500</span>
              <button
                className="primary"
                disabled={
                  busy ||
                  !text.trim() ||
                  (composerRevision !== null && composerRevision !== ticket.revision)
                }
              >
                <Send size={15} />
                {internal
                  ? 'Сохранить комментарий'
                  : ticket.demo
                    ? 'Сохранить демо-ответ'
                    : 'Утвердить и отправить'}
              </button>
            </div>
          </form>
        </div>
        <aside className="analysis-column">
          <div className="analysis-title">
            <div className="ai-symbol">
              <MessageSquare size={18} />
            </div>
            <h3>Support Copilot</h3>
            <span className="badge">
              {analysis?.provider === 'openai' ? 'AI' : 'Локальный режим'}
            </span>
          </div>
          <div className="tabs ai-tabs">
            <button
              className={aiTab === 'analysis' ? 'active' : ''}
              onClick={() => setAiTab('analysis')}
            >
              Разбор
            </button>
            <button
              className={aiTab === 'properties' ? 'active' : ''}
              onClick={() => setAiTab('properties')}
            >
              Параметры
            </button>
          </div>
          {aiTab === 'properties' ? (
            <div className="properties">
              <label>
                Статус
                <select
                  value={ticket.status}
                  disabled={busy}
                  onChange={(e) => patch({ status: e.target.value })}
                >
                  {Object.entries(statuses).map(([key, label]) => (
                    <option key={key} value={key} disabled={key === 'new' || key === 'analyzing'}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Категория
                <select
                  value={ticket.category}
                  disabled={busy}
                  onChange={(e) => patch({ category: e.target.value })}
                >
                  {Object.entries(categories).map(([key, label]) => (
                    <option key={key} value={key}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Приоритет
                <select
                  value={ticket.priority}
                  disabled={busy}
                  onChange={(e) => patch({ priority: e.target.value })}
                >
                  <option value="normal">Обычный</option>
                  <option value="high">Высокий</option>
                </select>
              </label>
              <label>
                Ответственный
                <select
                  value={ticket.assignee?.id || ''}
                  disabled={busy}
                  onChange={(e) => patch({ assignee_id: e.target.value || null })}
                >
                  <option value="">Не назначен</option>
                  {staff
                    .filter(
                      (s) =>
                        s.role === 'admin' ||
                        (ticket.profile && s.servers.includes(ticket.profile.server)),
                    )
                    .map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                </select>
              </label>
              <p className="muted">Изменения сохраняются сразу.</p>
            </div>
          ) : (
            <div className="analysis-content">
              {ticket.status === 'analyzing' && (
                <p role="status" className="processing">
                  <RefreshCw size={14} />
                  Готовим разбор…
                </p>
              )}
              {!analysis ? (
                <div className="analysis-empty">
                  <CircleHelp size={23} />
                  <p>
                    {ticket.status === 'analyzing'
                      ? 'Обращение сохранено. Результат появится после обработки.'
                      : 'Разбор пока не готов. Сотрудник может обработать обращение вручную.'}
                  </p>
                </div>
              ) : (
                <>
                  {analysis.stale && (
                    <p className="notice">
                      После разбора появились изменения. Запустите его снова перед использованием
                      черновика.
                    </p>
                  )}
                  <section>
                    <h4>Суть обращения</h4>
                    <p>{analysis.result.summary}</p>
                  </section>
                  {analysis.result.triage && (
                    <section>
                      <h4>Категория и приоритет</h4>
                      <p>{contractCategories[analysis.result.triage.category] || analysis.result.triage.category} · {analysis.result.triage.priority.toUpperCase()}</p>
                      <p className="muted">Заявленный ник: {analysis.result.triage.extracted.nickname || 'не указан'} · вложения: {analysis.result.triage.extracted.has_evidence ? 'есть, не просмотрены' : 'нет'}</p>
                    </section>
                  )}
                  {analysis.result.routing?.mode === 'human' &&
                    !analysis.result.escalation_reasons.length && (
                      <section className="human-review">
                        <h4>Нужен сотрудник</h4>
                        <p>{analysis.result.routing.reason}</p>
                      </section>
                    )}
                  <section>
                    <h4>Со слов игрока</h4>
                    <ul>
                      {analysis.result.claims.map((v, i) => (
                        <li key={i}>{v}</li>
                      ))}
                    </ul>
                  </section>
                  <section>
                    <h4>Подтверждённые факты</h4>
                    {analysis.result.verified_facts.length ? (
                      <ul>
                        {analysis.result.verified_facts.map((v, i) => (
                          <li key={i}>{v}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="muted">Нет. Игровые логи не подключены.</p>
                    )}
                  </section>
                  <section>
                    <h4>Нужно уточнить</h4>
                    <ul>
                      {analysis.result.missing.map((v, i) => (
                        <li key={i}>{v}</li>
                      ))}
                    </ul>
                  </section>
                  {analysis.result.routing?.mode === 'automatic' && (
                    <section className="auto-review">
                      <h4>
                        <Check size={14} />
                        Автоматический ответ
                      </h4>
                      <p>{analysis.result.routing.reason}</p>
                      <p className="muted">
                        Ответ сохранён в переписке вместе со статусом доставки.
                      </p>
                    </section>
                  )}
                  {!!analysis.result.escalation_reasons.length && (
                    <section className="human-review">
                      <h4>
                        <UserRound size={14} />
                        Нужен сотрудник
                      </h4>
                      <ul>
                        {analysis.result.escalation_reasons.map((v, i) => (
                          <li key={i}>{v}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                  <section>
                    <h4>
                      Источники <span>{analysis.sources.length}</span>
                    </h4>
                    {analysis.sources.length ? (
                      analysis.sources.map((s) => s.url ? (
                        <a
                          key={s.id}
                          className="source"
                          href={s.url || undefined}
                          target="_blank"
                          rel="noreferrer"
                        >
                          <BookOpen size={15} />
                          <span>
                            {s.clause ? `${s.clause} · ` : ''}
                            {s.title}
                            <small>
                              Редакция {s.version}
                              {analysis.result.rule_ids.includes(s.id)
                                ? ' · использован в ответе'
                                : ' · для проверки'}
                            </small>
                          </span>
                          {s.url && <ArrowUpRight size={14} />}
                        </a>
                      ) : (
                        <details key={s.id}>
                          <summary className="source"><BookOpen size={15} /><span>{s.clause ? `${s.clause} · ` : ''}{s.title}<small>Редакция {s.version}</small></span></summary>
                          <p className="source-text">{s.text}</p>
                        </details>
                      ))
                    ) : (
                      <p className="muted">Подходящих правил нет в утверждённой базе.</p>
                    )}
                  </section>
                  <section className="draft">
                    <h4>Черновик ответа</h4>
                    <p>{analysis.result.draft}</p>
                    <button
                      className="secondary"
                      disabled={!usableDraft || busy}
                      onClick={() => {
                        setText(analysis.result.draft);
                        setComposerRevision(ticket.revision);
                        setInternal(false);
                        requestKey.current = crypto.randomUUID();
                      }}
                    >
                      <FileText size={14} />
                      Использовать черновик
                    </button>
                    <small>Проверьте факты и формулировки перед отправкой.</small>
                  </section>
                </>
              )}
              <button
                className="text-button"
                onClick={() => act(`/tickets/${id}/analyze`, 'POST')}
                disabled={busy || ticket.status === 'analyzing'}
              >
                <RefreshCw size={14} />
                Повторить разбор
              </button>
              {ticket.jobs
                ?.filter((j) => j.state === 'failed' || j.state === 'uncertain')
                .map((j) => (
                  <p key={j.id} className="job-error">
                    {j.kind === 'analyze' ? 'Ошибка AI' : 'Ошибка доставки'} · {aiErrors[j.error || ""] || j.error}
                  </p>
                ))}
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null),
    closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const before = document.activeElement as HTMLElement;
    const first = ref.current?.querySelector<HTMLElement>('button,input');
    first?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeRef.current();
      if (e.key === 'Tab') {
        const fields = Array.from(
          ref.current?.querySelectorAll<HTMLElement>('button,input,textarea,select,a[href]') || [],
        ).filter((e) => !e.hasAttribute('disabled'));
        const a = fields[0],
          b = fields[fields.length - 1];
        if (e.shiftKey && document.activeElement === a) {
          e.preventDefault();
          b?.focus();
        } else if (!e.shiftKey && document.activeElement === b) {
          e.preventDefault();
          a?.focus();
        }
      }
    };
    document.addEventListener('keydown', key);
    return () => {
      document.removeEventListener('keydown', key);
      before?.focus();
    };
  }, []);
  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <header>
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="Закрыть">
            <X size={20} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}
function DemoModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (t: Ticket) => void;
}) {
  const [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    const data = Object.fromEntries(new FormData(e.currentTarget));
    try {
      onCreated(
        await api<Ticket>('/demo/tickets', {
          method: 'POST',
          body: JSON.stringify(data),
        }),
      );
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Тестовое обращение" onClose={onClose}>
      <p className="muted">Обращение будет помечено как демо. Ответы сохраняются в CRM.</p>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>
            Ник персонажа
            <input
              name="nickname"
              defaultValue="Alex_Walker"
              minLength={2}
              maxLength={100}
              required
            />
          </label>
          <label>
            Сервер
            <input name="server" defaultValue="Сервер 01" maxLength={80} required />
          </label>
        </div>
        <label>
          Категория
          <select name="category">
            {Object.entries(categories).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          Тип обращения
          <select name="intake">
            <option value="complaint">Жалоба · проверяет сотрудник</option>
            <option value="chat">Вопрос · автоответ разрешён</option>
          </select>
        </label>
        <label>
          Язык ответа
          <select name="language">
            <option value="ru">Русский</option>
            <option value="en">English</option>
            <option value="kk">Қазақша</option>
            <option value="uz">O‘zbekcha</option>
          </select>
        </label>
        <label>
          Описание
          <textarea
            name="text"
            rows={5}
            minLength={10}
            maxLength={10000}
            placeholder="Что произошло, где и когда?"
            required
          />
        </label>
        {error && <ErrorBox text={error} />}
        <button className="primary" disabled={busy}>
          {busy ? 'Создаём…' : 'Создать обращение'}
        </button>
      </form>
    </Modal>
  );
}
function RulesPage({ admin }: { admin: boolean }) {
  const [rules, setRules] = useState<Rule[]>([]),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false),
    [show, setShow] = useState(false);
  const load = useCallback(
    () =>
      api<Rule[]>('/rules')
        .then((r) => {
          setRules(r);
          setError('');
        })
        .catch((e) => setError(e.message)),
    [],
  );
  useEffect(() => {
    void load();
  }, [load]);
  const toggle = async (r: Rule) => {
    setBusy(true);
    try {
      await api(`/rules/${r.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ approved: !r.approved }),
      });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const add = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setBusy(true);
    const data = Object.fromEntries(new FormData(e.currentTarget));
    try {
      await api('/rules', {
        method: 'POST',
        body: JSON.stringify({ ...data, approved: false }),
      });
      setShow(false);
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="standalone">
      <div className="page-heading">
        <div>
          <h1>База правил</h1>
          <p>Версии источников, на которые опирается Support Copilot.</p>
        </div>
        {admin && (
          <button className="secondary" onClick={() => setShow(true)}>
            <Plus size={16} />
            Добавить редакцию
          </button>
        )}
      </div>
      <div className="knowledge-note">
        <BookOpen size={20} />
        <p>
          AI использует только утверждённые источники. Начальные статьи — справочные материалы;
          полный регламент проекта нужно добавить и проверить.
        </p>
      </div>
      {error && <ErrorBox text={error} retry={load} />}
      <div className="rules-list">
        {rules.map((r) => (
          <article className="rule-row" key={r.id}>
            <div>
              <div className="rule-heading">
                <h2>
                  {r.clause ? `${r.clause} · ` : ''}
                  {r.title}
                </h2>
                <span className={`badge ${r.approved ? 'status-resolved' : ''}`}>
                  {r.approved ? 'Утверждён' : 'На проверке'}
                </span>
              </div>
              <p>{r.text}</p>
              <div className="rule-meta">
                <span>
                  Редакция {r.version} · {r.language.toUpperCase()} ·{' '}
                  {r.server === '*' ? 'Все серверы' : r.server}
                </span>
                <a href={r.url} target="_blank" rel="noreferrer">
                  Открыть источник <ArrowUpRight size={14} />
                </a>
              </div>
            </div>
            {admin && (
              <button className="secondary" disabled={busy} onClick={() => toggle(r)}>
                {r.approved ? 'Снять с публикации' : 'Утвердить'}
              </button>
            )}
          </article>
        ))}
        {!rules.length && (
          <div className="empty">
            <h2>Источники ещё не добавлены</h2>
            <p>Загрузите правила проекта и утвердите их для использования в AI.</p>
          </div>
        )}
      </div>
      {show && (
        <Modal title="Новая редакция источника" onClose={() => setShow(false)}>
          <form onSubmit={add}>
            <label>
              Название
              <input name="title" required minLength={3} maxLength={200} />
            </label>
            <div className="form-grid">
              <label>
                Пункт правила
                <input name="clause" maxLength={80} />
              </label>
              <label>
                Редакция
                <input name="version" placeholder="2026-10-30" required maxLength={50} />
              </label>
            </div>
            <label>
              Ссылка на источник
              <input name="url" type="url" required />
            </label>
            <div className="form-grid">
              <label>
                Сервер
                <input name="server" defaultValue="*" required maxLength={80} />
              </label>
              <label>
                Язык
                <input name="language" defaultValue="ru" required maxLength={12} />
              </label>
            </div>
            <label>
              Текст
              <textarea name="text" minLength={20} maxLength={20000} rows={6} required />
            </label>
            {error && <ErrorBox text={error} />}
            <button className="primary" disabled={busy}>
              Добавить на проверку
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
function SystemPage({ system }: { system: System | null }) {
  return (
    <div className="standalone">
      <div className="page-heading">
        <div>
          <h1>Подключения</h1>
          <p>Состояние сервисов рабочего пространства.</p>
        </div>
      </div>
      {!system ? (
        <p>Загружаем состояние…</p>
      ) : (
        <div className="system-list">
          <section>
            <div>
              <h2>Языковая модель</h2>
              <p>Классификация, извлечение сведений и черновик.</p>
            </div>
            <div>
              <strong>
                {system.ai_provider === 'openai' ? 'OpenAI подключён' : 'Локальный режим'}
              </strong>
              <p>
                {system.auto_reply_enabled && system.ai_provider === 'openai'
                  ? 'Простые вопросы и безобидные реплики: автоответы включены.'
                  : 'Автоответы не выполняются; обращения проверяет сотрудник.'}
              </p>
              <p>
                {system.ai_provider === 'openai'
                  ? 'Разбор обращений выполняется внешней моделью.'
                  : 'Без вызова модели: текст обращения и шаблон ответа. Для AI задайте ключ и модель на сервере.'}
              </p>
            </div>
          </section>
          <section>
            <div>
              <h2>Telegram</h2>
              <p>Приём обращений и доставка ответов.</p>
            </div>
            <div>
              <strong>{system.telegram_configured ? 'Токен настроен' : 'Токен не настроен'}</strong>
              <p>
                Для получения сообщений запустите polling или настройте webhook. Ответы отправляет
                фоновый worker.
              </p>
            </div>
          </section>
          <section>
            <div>
              <h2>Игровой профиль</h2>
              <p>Принадлежность аккаунта и персонажа.</p>
            </div>
            <div>
              <strong>Ожидает интеграции Grand Mobile</strong>
              <p>
                Указанный игроком ник и сервер сохраняются с отметкой «не подтверждён». Для проверки
                нужен официальный API или одноразовый код из игры.
              </p>
            </div>
          </section>
          <section>
            <div>
              <h2>Материалы жалоб</h2>
              <p>Скриншоты и документы игроков.</p>
            </div>
            <div>
              <strong>Защищённая загрузка из Telegram</strong>
              <p>
                Файлы доступны сотрудникам с доступом к обращению. AI анализирует текст; видео и
                изображения проверяет человек.
              </p>
            </div>
          </section>
          <section>
            <div>
              <h2>Фоновая обработка</h2>
              <p>Задачи анализа и отправки.</p>
            </div>
            <div>
              <strong>
                {system.failed_jobs === null
                  ? 'Состояние доступно администратору'
                  : `Требуют внимания: ${system.failed_jobs}`}
              </strong>
              <p>Ошибки и результат доставки отображаются в карточке обращения.</p>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}

createRoot(document.getElementById('root')!).render(<App />);
