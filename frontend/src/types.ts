export type Staff = {
  id: string;
  name: string;
  login: string;
  role: string;
  servers: string[];
};
export type Auth = { staff: Staff; csrf: string };
export type System = {
  ai_provider: string;
  telegram_configured: boolean;
  demo_enabled: boolean;
  auto_reply_enabled: boolean;
  profile_verification: string;
  servers: string[];
  failed_jobs: number | null;
};
export type Source = {
  id: string;
  title: string;
  clause: string;
  text: string;
  url: string;
  version: string;
};
export type Rule = Source & {
  approved: boolean;
  language: string;
  server: string;
};
export type Analysis = {
  id: string;
  revision: number;
  provider: string;
  stale: boolean;
  result: {
    language: string;
    category: string;
    summary: string;
    claims: string[];
    verified_facts: string[];
    missing: string[];
    escalation_reasons: string[];
    draft: string;
    rule_ids: string[];
    routing?: { mode: 'automatic' | 'human'; reason: string };
    triage?: { category: string; priority: string; confidence: number; extracted: { nickname: string | null; has_evidence: boolean; rule_refs: string[] } };
  };
  sources: Source[];
};
export type Ticket = {
  id: number;
  title: string;
  intake: 'chat' | 'complaint';
  category: string;
  status: string;
  priority: string;
  revision: number;
  demo: boolean;
  parent_id: number | null;
  created_at: string;
  updated_at: string;
  player: { name: string; language: string };
  profile: {
    id: string;
    nickname: string;
    server: string;
    verified: boolean;
  } | null;
  assignee: Staff | null;
  analysis?: Analysis | null;
  messages?: {
    id: string;
    author: string;
    text: string;
    delivery: string | null;
    created_at: string;
  }[];
  attachments?: { id: string; name: string; size: number; mime: string }[];
  audit?: { actor: string; action: string; created_at: string }[];
  jobs?: {
    id: string;
    kind: string;
    state: string;
    attempts: number;
    error: string | null;
  }[];
};
export const categories: Record<string, string> = {
  player: 'Жалоба на игрока',
  admin: 'Действия администрации',
  appeal: 'Апелляция',
  account: 'Игровой аккаунт',
  payment: 'Платёж',
  technical: 'Техническая проблема',
  other: 'Другое',
};
export const contractCategories: Record<string, string> = {
  'complaint.insult': 'Оскорбления', 'complaint.cheat': 'Читы',
  'complaint.dm': 'DM и нарушение РП', 'complaint.scam': 'Мошенничество',
  'complaint.rmt_ads': 'RMT и реклама', 'complaint.admin': 'Жалоба на администратора',
  'complaint.other': 'Другое нарушение', 'complaint.invalid': 'Неполная жалоба',
  'report.question': 'Вопрос об игре', 'report.help': 'Помощь и баги',
  'report.complaint': 'Жалоба через репорт', 'report.account': 'Аккаунт',
  'report.payment': 'Платёж', 'report.offtopic': 'Оффтоп',
};
export const aiErrors: Record<string, string> = {
  provider_http_429: 'OpenAI ограничил запросы; проверьте квоту и лимиты проекта',
  provider_daily_quota_exhausted: 'Исчерпан дневной лимит OpenAI',
  provider_billing_quota_exhausted: 'Исчерпана квота или лимит расходов OpenAI',
  handout_not_loaded: 'Импортируйте архив организаторов и перезапустите сервис',
  provider_http_401: 'OpenAI отклонил API-ключ',
  provider_timeout: 'OpenAI не ответил вовремя',
  unsafe_draft_claim: 'Черновик отклонён: неподтверждённое действие или обещание',
  unknown_rule_reference: 'Черновик отклонён: неизвестный пункт правил',
};
export const statuses: Record<string, string> = {
  new: 'Новое',
  analyzing: 'Разбор AI',
  needs_info: 'Ждём игрока',
  review: 'На проверке',
  in_progress: 'В работе',
  resolved: 'Решено',
  closed: 'Закрыто',
};
export const delivery: Record<string, string> = {
  queued: 'В очереди отправки',
  sent: 'Доставлено в Telegram',
  failed: 'Не доставлено',
  uncertain: 'Доставка не подтверждена. Проверьте Telegram перед новой отправкой.',
  demo: 'Демо · сохранено без отправки',
  cancelled: 'Автоответ отменён: появились новые данные или подключился сотрудник',
};
