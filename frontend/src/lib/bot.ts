const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    cache: 'no-store',
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(text || `${res.status}`);
  }
  return res.json();
}

export interface DialogMessage {
  id: number;
  role: 'user' | 'assistant' | 'system' | 'operator' | string;
  content: string;
  agent_name: string | null;
  created_at: string | null;
}

export interface DialogFinance {
  ai_cost_usd: number;
  ai_tokens: number;
  income_usd: number;
  manual_expense_usd: number;
  expense_usd: number;
  profit_usd: number;
}

export interface DialogOrder {
  id: number;
  dialog_id: number;
  amount_usdt: number;
  description: string;
  payment_method: string;
  payment_status: string;
  wallet_address: string | null;
  tx_hash: string | null;
  escrow_url: string | null;
  created_at: string | null;
  paid_at: string | null;
}

export interface LedgerEntry {
  id: number;
  dialog_id: number | null;
  order_id?: number | null;
  type: 'income' | 'expense' | 'refund' | string;
  amount_usd: number;
  currency: string;
  network: string | null;
  tx_hash: string | null;
  description: string;
  created_at: string | null;
}

export interface DialogCard {
  id: number;
  telegram_user_id: number;
  telegram_username: string | null;
  username?: string | null;
  first_name: string | null;
  funnel_stage: string;
  work_status: string;
  ai_active: boolean;
  quoted_price_usd: number | null;
  quoted_days: number | null;
  estimated_price_usd?: number | null;
  quoted_price_max_usd?: number | null;
  price_approved?: boolean;
  tz_summary?: string;
  admin_task_summary?: string;
  client_offer_pitch?: string;
  awaiting_admin_quote?: boolean;
  followup_count: number;
  followup_mode: string;
  next_followup_at: string | null;
  custom_followup_at?: string | null;
  silent_until_completed?: boolean;
  last_message_at: string | null;
  last_user_message_at?: string | null;
  created_at?: string | null;
  is_business: boolean;
  business_connection_id?: string | null;
  telegram_link: string;
  account_label: string;
  message_count?: number;
  last_message_preview?: string | null;
  client_profile?: Record<string, unknown>;
}

export interface DialogDetail extends DialogCard {
  last_followup_at?: string | null;
  finance: DialogFinance;
  orders: DialogOrder[];
  ledger: LedgerEntry[];
  messages: DialogMessage[];
}

export interface BotStats {
  dialogs: number;
  in_progress: number;
  payment_pending: number;
  revenue_usdt: number;
  ledger_usd: number;
  income_usd?: number;
  expense_usd?: number;
}

export interface PaymentTemplate {
  id: number;
  network_key: string;
  label: string;
  wallet_address: string;
  message_template: string;
  enabled: boolean;
}

export const WORK_STATUSES = [
  { id: 'lead', label: 'Лид' },
  { id: 'quoting', label: 'Обсуждение' },
  { id: 'awaiting_admin', label: 'Ждём цену (админ)' },
  { id: 'payment_pending', label: 'Ждём оплату' },
  { id: 'paid', label: 'Оплачено' },
  { id: 'in_progress', label: 'На работе' },
  { id: 'completed', label: 'Выполнен' },
  { id: 'paused', label: 'Пауза' },
  { id: 'lost', label: 'Потерян' },
];

export const FOLLOWUP_MODES = [
  { id: 'none', label: 'Выкл' },
  { id: 'standard', label: 'Стандарт (3д)' },
  { id: 'same_day', label: 'В тот же день' },
  { id: 'custom', label: 'Дата' },
  { id: 'vacation', label: 'Отпуск (7д)' },
];

export const FUNNEL_STAGES = [
  { id: 'new', label: 'Новый' },
  { id: 'qualification', label: 'Квалификация' },
  { id: 'consultation', label: 'Консультация' },
  { id: 'negotiation', label: 'Переговоры' },
  { id: 'payment_pending', label: 'Ждём оплату' },
  { id: 'paid', label: 'Оплачено' },
  { id: 'escrow', label: 'Эскроу' },
  { id: 'escrow_draft', label: 'Черновик эскроу' },
  { id: 'completed', label: 'Завершён' },
  { id: 'lost', label: 'Потерян' },
];

export function clientName(d: Pick<DialogCard, 'first_name' | 'telegram_username' | 'username' | 'telegram_user_id'>) {
  return d.first_name || d.telegram_username || d.username || `ID ${d.telegram_user_id}`;
}

export const dialogs = {
  list: (limit = 100) => api<DialogCard[]>(`/api/dialogs?limit=${limit}`),
  get: (id: number) => api<DialogDetail>(`/api/dialogs/${id}`),
  send: (id: number, content: string) =>
    api<{ ok: boolean; message: DialogMessage }>(`/api/dialogs/${id}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }),
  setAI: (id: number, ai_active: boolean) =>
    api(`/api/dialogs/${id}/ai`, {
      method: 'PATCH',
      body: JSON.stringify({ ai_active }),
    }),
  setWorkStatus: (id: number, work_status: string) =>
    api(`/api/dialogs/${id}/work-status`, {
      method: 'PATCH',
      body: JSON.stringify({ work_status }),
    }),
  patchFollowup: (
    id: number,
    body: {
      followup_mode?: string;
      next_followup_at?: string | null;
      custom_followup_at?: string | null;
      disable?: boolean;
    }
  ) =>
    api<DialogCard>(`/api/dialogs/${id}/followup`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  patchQuote: (
    id: number,
    body: {
      quoted_price_usd?: number | null;
      quoted_price_max_usd?: number | null;
      quoted_days?: number | null;
      tz_summary?: string;
      admin_task_summary?: string;
      client_offer_pitch?: string;
      work_status?: string;
      funnel_stage?: string;
      price_approved?: boolean;
      send_offer?: boolean;
    }
  ) =>
    api<DialogCard & { sent_offer?: string }>(`/api/dialogs/${id}/quote`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  sendOffer: (id: number) =>
    api<{ ok: boolean; offer: string; dialog: DialogCard }>(`/api/dialogs/${id}/send-offer`, {
      method: 'POST',
    }),
  orders: (dialogId?: number) =>
    api<DialogOrder[]>(dialogId != null ? `/api/orders?dialog_id=${dialogId}` : '/api/orders'),
  escrowDrafts: () => api<Record<string, unknown>[]>('/api/escrow/drafts'),
};

export const bot = {
  clients: () => api<DialogCard[]>('/api/bot/clients'),
  client: (id: number) => api<DialogDetail>(`/api/bot/clients/${id}`),
  stats: () => api<BotStats>('/api/bot/stats'),
  templates: () => api<PaymentTemplate[]>('/api/bot/payment-templates'),
  patchTemplate: (id: number, body: Partial<PaymentTemplate>) =>
    api<PaymentTemplate>(`/api/bot/payment-templates/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  ledger: (dialogId?: number) =>
    api<LedgerEntry[]>(
      dialogId != null ? `/api/bot/ledger?dialog_id=${dialogId}` : '/api/bot/ledger'
    ),
  addLedger: (body: {
    dialog_id: number;
    type: 'income' | 'expense' | 'refund';
    amount_usd: number;
    currency?: string;
    network?: string;
    tx_hash?: string;
    description?: string;
  }) =>
    api<LedgerEntry>('/api/bot/ledger', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  setWorkStatus: (dialogId: number, work_status: string) =>
    dialogs.setWorkStatus(dialogId, work_status),
};

export interface TelegramStatus {
  token_set: boolean;
  admin_id: number | null;
  running: boolean;
  connections: Array<{
    connection_id: string;
    owner_id: number;
    user_chat_id: number | null;
    is_enabled: boolean;
    can_reply: boolean;
    live_can_reply: boolean | null;
    live_is_enabled: boolean | null;
    block_reason: string | null;
  }>;
  blocked_by_can_reply: boolean;
  live_errors: string[];
  runtime: {
    reply_delay_min_sec: number;
    reply_delay_max_sec: number;
    force_business_reply: boolean;
    global_ai_enabled: boolean;
    max_followups: number;
    followup_delays: string;
    tone: string;
  };
  howto_fix_reply: string;
}

export const telegram = {
  status: () => api<TelegramStatus>('/api/telegram/status'),
  refresh: () => api<TelegramStatus>('/api/telegram/refresh', { method: 'POST' }),
  patchRuntime: (body: Partial<TelegramStatus['runtime']>) =>
    api<TelegramStatus['runtime']>('/api/telegram/runtime', {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  aiReply: (dialogId: number) =>
    api<{
      ok: boolean;
      draft?: boolean;
      reply: string;
      sent: boolean;
      send_error: string | null;
      hint: string | null;
      user_message?: string;
    }>(`/api/telegram/dialogs/${dialogId}/ai-reply`, { method: 'POST' }),
  testSend: () =>
    api<{ ok: boolean; target?: string; error?: string; hint?: string }>('/api/telegram/test-send', {
      method: 'POST',
    }),
};
