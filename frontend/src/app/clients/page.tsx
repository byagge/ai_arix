'use client';

import Link from 'next/link';
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  IconChevronLeft,
  IconExternal,
  IconSearch,
  IconSend,
  IconX,
} from '@/components/icons';
import { Pill, Spinner, Toggle } from '@/components/ui/Primitives';
import {
  DialogCard,
  DialogDetail,
  DialogMessage,
  FOLLOWUP_MODES,
  FUNNEL_STAGES,
  WORK_STATUSES,
  bot,
  clientName,
  dialogs,
  telegram,
} from '@/lib/bot';

function fmtTime(iso: string | null | undefined) {
  if (!iso) return '';
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  return sameDay
    ? d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
    : d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' });
}

function fmtFull(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function money(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—';
  return `$${n.toFixed(2)}`;
}

function statusLabel(id: string) {
  return WORK_STATUSES.find((s) => s.id === id)?.label || id;
}

function funnelLabel(id: string) {
  return FUNNEL_STAGES.find((s) => s.id === id)?.label || id;
}

function initials(name: string) {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() || '')
    .join('') || '?';
}

export default function ClientsPage() {
  const [list, setList] = useState<DialogCard[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<DialogDetail | null>(null);
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const loadList = useCallback(async () => {
    try {
      const rows = await dialogs.list(150);
      setList(rows);
      setError(null);
    } catch {
      setError('Не удалось загрузить диалоги');
    }
  }, []);

  const loadDetail = useCallback(async (id: number, soft = false) => {
    if (!soft) setLoadingDetail(true);
    try {
      const d = await dialogs.get(id);
      setDetail(d);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка загрузки чата');
    } finally {
      if (!soft) setLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    loadList();
    const id = setInterval(loadList, 4000);
    return () => clearInterval(id);
  }, [loadList]);

  // Deep-link + keep URL in sync for mobile bottom-bar hide
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const params = new URLSearchParams(window.location.search);
    const id = Number(params.get('id'));
    if (id && !Number.isNaN(id)) {
      setSelectedId(id);
    }
  }, []);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const url = new URL(window.location.href);
    if (selectedId != null) {
      url.searchParams.set('id', String(selectedId));
    } else {
      url.searchParams.delete('id');
    }
    window.history.replaceState({}, '', `${url.pathname}${url.search}`);
  }, [selectedId]);

  useEffect(() => {
    if (selectedId == null) return;
    loadDetail(selectedId);
    const id = setInterval(() => loadDetail(selectedId, true), 2000);
    return () => clearInterval(id);
  }, [selectedId, loadDetail]);

  // Live updates via websocket — show incoming messages before AI replies
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
    const wsUrl = apiBase.replace(/^http/, 'ws') + '/api/ws';
    let ws: WebSocket | null = null;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (closed) return;
      try {
        ws = new WebSocket(wsUrl);
      } catch {
        retry = setTimeout(connect, 3000);
        return;
      }
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          const type = data.event_type || data.type;
          const dialogId = data.dialog_id;
          if (
            type === 'message_received' ||
            type === 'agent_response' ||
            type === 'admin_summary_updated' ||
            type === 'requirements_complete'
          ) {
            loadList();
            if (selectedId != null && (dialogId == null || dialogId === selectedId)) {
              loadDetail(selectedId, true);
            }
          }
        } catch {
          /* ignore */
        }
      };
      ws.onclose = () => {
        if (!closed) retry = setTimeout(connect, 2500);
      };
      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          /* ignore */
        }
      };
    };
    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  }, [selectedId, loadList, loadDetail]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [detail?.messages?.length, selectedId]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return list;
    return list.filter((d) => {
      const name = clientName(d).toLowerCase();
      const user = (d.telegram_username || d.username || '').toLowerCase();
      const prev = (d.last_message_preview || '').toLowerCase();
      return name.includes(q) || user.includes(q) || prev.includes(q) || String(d.telegram_user_id).includes(q);
    });
  }, [list, query]);

  const select = (id: number) => {
    setSelectedId(id);
    setProfileOpen(false);
    setDraft('');
  };

  const backToList = () => {
    setSelectedId(null);
    setDetail(null);
    setProfileOpen(false);
    setDraft('');
  };

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!selectedId || !draft.trim() || sending) return;
    const content = draft.trim();
    setDraft('');
    setSending(true);
    // optimistic
    const optimistic: DialogMessage = {
      id: Date.now(),
      role: 'operator',
      content,
      agent_name: null,
      created_at: new Date().toISOString(),
    };
    setDetail((prev) =>
      prev ? { ...prev, messages: [...prev.messages, optimistic] } : prev
    );
    try {
      const res = await dialogs.send(selectedId, content);
      setDetail((prev) => {
        if (!prev) return prev;
        const msgs = prev.messages.filter((m) => m.id !== optimistic.id);
        return { ...prev, messages: [...msgs, res.message] };
      });
      loadList();
    } catch (err) {
      setDetail((prev) =>
        prev
          ? { ...prev, messages: prev.messages.filter((m) => m.id !== optimistic.id) }
          : prev
      );
      setDraft(content);
      setError(err instanceof Error ? err.message : 'Не удалось отправить');
    } finally {
      setSending(false);
    }
  };

  const refreshAll = async () => {
    await loadList();
    if (selectedId) await loadDetail(selectedId, true);
  };

  return (
    <div className="messenger flex h-full overflow-hidden bg-bg md:h-screen">
      {/* Left: chat list — full screen on mobile when no chat open */}
      <aside
        className={[
          'flex w-full shrink-0 flex-col border-r border-border-soft bg-bg-rail md:w-[300px]',
          selectedId ? 'hidden md:flex' : 'flex',
        ].join(' ')}
      >
        <div className="border-b border-border-soft px-3 py-3 safe-pt">
          <div className="mb-2.5 flex items-center justify-between">
            <h1 className="text-[17px] font-semibold tracking-tight md:text-[15px]">Чаты</h1>
            <span className="oai-badge">{list.length}</span>
          </div>
          <div className="oai-search-box !cursor-text">
            <IconSearch size={14} className="shrink-0 opacity-60" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Поиск"
              className="min-w-0 flex-1 bg-transparent text-[13px] outline-none placeholder:text-fg-muted"
            />
          </div>
        </div>

        <div className="oai-scroll flex-1 overflow-y-auto pb-[calc(4.5rem+env(safe-area-inset-bottom))] md:pb-0">
          {filtered.map((d) => {
            const active = d.id === selectedId;
            const name = clientName(d);
            return (
              <button
                key={d.id}
                type="button"
                onClick={() => select(d.id)}
                className={[
                  'flex w-full gap-3 border-b border-border-soft px-3 py-3 text-left transition-colors md:gap-2.5 md:py-2.5',
                  active ? 'bg-bg-active' : 'active:bg-bg-hover md:hover:bg-bg-hover',
                ].join(' ')}
              >
                <span
                  className={[
                    'mt-0.5 grid h-12 w-12 shrink-0 place-items-center rounded-full text-[13px] font-semibold md:h-10 md:w-10 md:text-[12px]',
                    d.ai_active
                      ? 'bg-accent/20 text-accent'
                      : 'bg-bg-surface3 text-fg-secondary',
                  ].join(' ')}
                >
                  {initials(name)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-[15px] font-medium md:text-[13.5px]">{name}</span>
                    <span className="ml-auto shrink-0 text-[11px] text-fg-muted">
                      {fmtTime(d.last_message_at)}
                    </span>
                  </span>
                  <span className="mt-0.5 flex items-center gap-1.5">
                    <span className="truncate text-[13px] text-fg-tertiary md:text-[12px]">
                      {d.last_message_preview || 'Нет сообщений'}
                    </span>
                  </span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    <span className="oai-badge !px-1.5 !py-0 text-[10px]">
                      {statusLabel(d.work_status)}
                    </span>
                    {!d.ai_active && (
                      <span className="oai-badge oai-badge-warn !px-1.5 !py-0 text-[10px]">
                        AI off
                      </span>
                    )}
                  </span>
                </span>
              </button>
            );
          })}
          {filtered.length === 0 && (
            <p className="px-4 py-10 text-center text-[13px] text-fg-tertiary">
              {error || 'Диалогов нет'}
            </p>
          )}
        </div>
      </aside>

      {/* Center: chat — full screen on mobile when open */}
      <section
        className={[
          'min-w-0 flex-1 flex-col',
          selectedId ? 'flex' : 'hidden md:flex',
        ].join(' ')}
      >
        {!selectedId || !detail ? (
          <div className="hidden flex-1 flex-col items-center justify-center gap-2 text-fg-tertiary md:flex">
            <p className="text-[14px] font-medium text-fg-secondary">Выберите диалог</p>
            <p className="text-[13px]">Слева — клиенты, справа откроется чат</p>
            {error && <p className="mt-2 text-[12px] text-danger">{error}</p>}
          </div>
        ) : (
          <>
            <header className="flex h-14 shrink-0 items-center gap-2 border-b border-border-soft px-2 safe-pt md:gap-3 md:px-4">
              <button
                type="button"
                onClick={backToList}
                className="oai-icon-btn md:hidden"
                aria-label="Назад к чатам"
              >
                <IconChevronLeft size={22} />
              </button>
              <button
                type="button"
                onClick={() => setProfileOpen(true)}
                className="flex min-w-0 flex-1 items-center gap-2.5 rounded-md px-1 py-1 text-left transition-colors hover:bg-bg-hover"
              >
                <span className="grid h-9 w-9 place-items-center rounded-full bg-accent/20 text-[12px] font-semibold text-accent">
                  {initials(clientName(detail))}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[15px] font-semibold md:text-[14px]">
                    {clientName(detail)}
                  </span>
                  <span className="block truncate text-[11.5px] text-fg-muted">
                    {detail.telegram_username ? `@${detail.telegram_username}` : detail.telegram_user_id}
                    <span className="hidden md:inline">
                      {' · '}
                      {detail.account_label}
                      {' · '}
                      {detail.ai_active ? 'AI вкл' : 'AI выкл'}
                    </span>
                    <span className="md:hidden">
                      {' · '}
                      {detail.ai_active ? 'в сети' : 'оператор'}
                    </span>
                  </span>
                </span>
              </button>
              <div className="ml-auto hidden items-center gap-2 md:flex">
                <Pill tone={detail.ai_active ? 'ok' : 'warn'}>
                  {detail.ai_active ? 'AI' : 'Оператор'}
                </Pill>
                <Pill>{statusLabel(detail.work_status)}</Pill>
              </div>
            </header>

            <div
              ref={scrollRef}
              className="oai-scroll messenger-thread relative flex-1 overflow-y-auto px-3 py-3 md:px-4 md:py-4"
            >
              {loadingDetail && detail.messages.length === 0 ? (
                <div className="flex h-full items-center justify-center text-fg-tertiary">
                  <Spinner size={16} />
                </div>
              ) : (
                <div className="mx-auto flex max-w-[720px] flex-col gap-1.5 md:gap-2.5">
                  {[...detail.messages]
                    .sort(
                      (a, b) =>
                        new Date(a.created_at || 0).getTime() -
                        new Date(b.created_at || 0).getTime()
                    )
                    .map((m) => (
                      <Bubble key={m.id} msg={m} />
                    ))}
                </div>
              )}
            </div>

            <form
              onSubmit={send}
              className="messenger-composer shrink-0 border-t border-border-soft bg-bg px-3 py-2 md:px-4 md:py-3"
            >
              <div className="mx-auto flex max-w-[720px] items-end gap-2">
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  rows={1}
                  placeholder="Сообщение…"
                  className="oai-textarea max-h-32 min-h-[44px] flex-1 resize-none !rounded-2xl !font-sans text-[15px] md:min-h-[42px] md:!rounded-md md:text-[13.5px]"
                />
                <button
                  type="submit"
                  disabled={!draft.trim() || sending}
                  className="oai-btn-primary h-11 w-11 shrink-0 !rounded-full !px-0 md:h-[42px] md:w-[42px] md:!rounded-md"
                  title="Отправить в Telegram"
                >
                  {sending ? <Spinner size={14} /> : <IconSend size={16} />}
                </button>
              </div>
              <p className="mx-auto mt-1.5 hidden max-w-[720px] text-[11px] text-fg-muted md:block">
                Enter — отправить · Shift+Enter — новая строка · сообщение уходит в реальный чат
              </p>
            </form>
          </>
        )}
      </section>

      {/* Right profile — desktop sidebar / mobile full-screen sheet */}
      {profileOpen && detail && (
        <ProfileSidebar
          detail={detail}
          onClose={() => setProfileOpen(false)}
          onUpdated={async () => {
            await refreshAll();
          }}
          setDetail={setDetail}
        />
      )}
    </div>
  );
}

function Bubble({ msg }: { msg: DialogMessage }) {
  const role = msg.role;
  const isUser = role === 'user';
  const isOp = role === 'operator';
  const isAI = role === 'assistant';
  const isSys = role === 'system';

  if (isSys) {
    return (
      <div className="my-1 text-center text-[11.5px] text-fg-muted">{msg.content}</div>
    );
  }

  return (
    <div className={`flex ${isUser ? 'justify-start' : 'justify-end'}`}>
      <div
        className={[
          'max-w-[85%] rounded-2xl px-3.5 py-2 text-[15px] leading-snug md:max-w-[78%] md:text-[13.5px] md:leading-relaxed',
          isUser
            ? 'rounded-bl-md bg-bg-accent text-fg'
            : isOp
              ? 'rounded-br-md bg-white text-[#0d0d0d]'
              : 'rounded-br-md bg-accent/25 text-fg',
        ].join(' ')}
      >
        <div className="mb-0.5 flex items-center gap-1.5 text-[10.5px] font-medium uppercase tracking-wide opacity-60">
          {isUser && 'Клиент'}
          {isOp && 'Оператор'}
          {isAI && (msg.agent_name || 'ИИ')}
          <span className="ml-auto font-normal normal-case tracking-normal">
            {fmtTime(msg.created_at)}
          </span>
        </div>
        <div className="whitespace-pre-wrap break-words">{msg.content}</div>
      </div>
    </div>
  );
}

function ProfileSidebar({
  detail,
  onClose,
  onUpdated,
  setDetail,
}: {
  detail: DialogDetail;
  onClose: () => void;
  onUpdated: () => Promise<void>;
  setDetail: React.Dispatch<React.SetStateAction<DialogDetail | null>>;
}) {
  const [busy, setBusy] = useState(false);
  const [price, setPrice] = useState(String(detail.quoted_price_usd ?? ''));
  const [priceMax, setPriceMax] = useState(String(detail.quoted_price_max_usd ?? ''));
  const [days, setDays] = useState(String(detail.quoted_days ?? ''));
  const [tz, setTz] = useState(detail.tz_summary || '');
  const [pitch, setPitch] = useState(detail.client_offer_pitch || '');
  const [ledgerType, setLedgerType] = useState<'income' | 'expense'>('expense');
  const [ledgerAmount, setLedgerAmount] = useState('');
  const [ledgerDesc, setLedgerDesc] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const [aiModal, setAiModal] = useState<{
    open: boolean;
    text: string;
    userMessage: string;
    generating: boolean;
  }>({ open: false, text: '', userMessage: '', generating: false });

  useEffect(() => {
    const est =
      detail.quoted_price_usd != null
        ? String(detail.quoted_price_usd)
        : detail.estimated_price_usd != null
          ? String(detail.estimated_price_usd)
          : '';
    setPrice(est);
    setPriceMax(String(detail.quoted_price_max_usd ?? ''));
    setDays(String(detail.quoted_days ?? ''));
    setTz(detail.admin_task_summary || detail.tz_summary || '');
    setPitch(detail.client_offer_pitch || '');
  }, [
    detail.id,
    detail.quoted_price_usd,
    detail.quoted_price_max_usd,
    detail.quoted_days,
    detail.tz_summary,
    detail.admin_task_summary,
    detail.client_offer_pitch,
    detail.estimated_price_usd,
  ]);

  const patch = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      const fresh = await dialogs.get(detail.id);
      setDetail(fresh);
      await onUpdated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Ошибка');
    } finally {
      setBusy(false);
    }
  };

  const openAiDraft = async () => {
    setAiModal({ open: true, text: '', userMessage: '', generating: true });
    setErr(null);
    try {
      const r = await telegram.aiReply(detail.id);
      setAiModal({
        open: true,
        text: r.reply || '',
        userMessage: r.user_message || '',
        generating: false,
      });
    } catch (e) {
      setAiModal({ open: false, text: '', userMessage: '', generating: false });
      setErr(e instanceof Error ? e.message : 'Не удалось сгенерировать');
    }
  };

  const sendAiDraft = async () => {
    const content = aiModal.text.trim();
    if (!content) return;
    setBusy(true);
    setErr(null);
    try {
      await dialogs.send(detail.id, content);
      setAiModal({ open: false, text: '', userMessage: '', generating: false });
      const fresh = await dialogs.get(detail.id);
      setDetail(fresh);
      await onUpdated();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Не удалось отправить');
    } finally {
      setBusy(false);
    }
  };

  const copyAiDraft = async () => {
    try {
      await navigator.clipboard.writeText(aiModal.text);
    } catch {
      setErr('Не удалось скопировать');
    }
  };

  const finance = detail.finance;

  return (
    <aside className="fixed inset-0 z-[60] flex w-full flex-col border-l border-border-soft bg-bg-rail animate-fade-in md:static md:inset-auto md:z-auto md:w-[340px] md:shrink-0">
      <div className="flex h-14 items-center justify-between border-b border-border-soft px-4 safe-pt">
        <h2 className="text-[14px] font-semibold">Клиент</h2>
        <button type="button" className="oai-icon-btn" onClick={onClose} title="Закрыть">
          <IconX size={16} />
        </button>
      </div>

      <div className="oai-scroll flex-1 space-y-5 overflow-y-auto px-4 py-4">
        {err && (
          <p className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-[12px] text-[#ffa2a5]">
            {err}
          </p>
        )}

        <section>
          <div className="mb-3 flex items-center gap-3">
            <span className="grid h-12 w-12 place-items-center rounded-full bg-accent/20 text-[14px] font-semibold text-accent">
              {initials(clientName(detail))}
            </span>
            <div className="min-w-0">
              <div className="truncate text-[15px] font-semibold">{clientName(detail)}</div>
              <a
                href={detail.telegram_link}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-[12.5px] text-accent no-underline hover:underline"
              >
                {detail.telegram_username ? `@${detail.telegram_username}` : 'Открыть в Telegram'}
                <IconExternal size={11} />
              </a>
            </div>
          </div>
          <KV label="Аккаунт" value={detail.account_label} />
          <KV label="Telegram ID" value={String(detail.telegram_user_id)} mono />
          <KV label="Первый контакт" value={fmtFull(detail.created_at)} />
          <KV label="Последний контакт" value={fmtFull(detail.last_message_at)} />
          <KV label="Последнее от клиента" value={fmtFull(detail.last_user_message_at)} />
        </section>

        <section className="border-t border-border-soft pt-4">
          <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-fg-muted">
            Управление
          </h3>
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <div className="text-[13px] font-medium">ИИ-агент</div>
              <div className="text-[11.5px] text-fg-muted">Автоответы в этом чате</div>
            </div>
            <Toggle
              checked={detail.ai_active}
              onChange={(v) => patch(() => dialogs.setAI(detail.id, v))}
            />
          </div>

          <button
            type="button"
            className="oai-btn-secondary mb-3 w-full"
            disabled={busy || aiModal.generating}
            onClick={openAiDraft}
          >
            {aiModal.generating ? 'Генерация…' : 'Сгенерировать ответ ИИ'}
          </button>
          {detail.is_business && (
            <p className="mb-3 text-[11.5px] text-fg-muted">
              Черновик откроется в окне — правьте и жмите «Отправить» или «Копировать».
            </p>
          )}

          <label className="mb-1.5 block text-[12px] text-fg-secondary">Этап работы</label>
          <select
            className="oai-select mb-3"
            value={detail.work_status}
            disabled={busy}
            onChange={(e) =>
              patch(() => dialogs.setWorkStatus(detail.id, e.target.value))
            }
          >
            {WORK_STATUSES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>

          <label className="mb-1.5 block text-[12px] text-fg-secondary">Воронка</label>
          <select
            className="oai-select mb-3"
            value={detail.funnel_stage}
            disabled={busy}
            onChange={(e) =>
              patch(() => dialogs.patchQuote(detail.id, { funnel_stage: e.target.value }))
            }
          >
            {FUNNEL_STAGES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </section>

        <section className="border-t border-border-soft pt-4">
          <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-fg-muted">
            Follow-up
          </h3>
          <KV label="Отправлено" value={String(detail.followup_count)} />
          <KV label="Последний" value={fmtFull(detail.last_followup_at)} />
          <KV label="Следующий" value={fmtFull(detail.next_followup_at)} />

          <div className="mb-3 mt-2 flex items-center justify-between gap-3">
            <div>
              <div className="text-[13px] font-medium">Follow-up</div>
              <div className="text-[11.5px] text-fg-muted">
                {detail.followup_mode === 'none' ? 'Отключён' : 'Активен'}
              </div>
            </div>
            <Toggle
              checked={detail.followup_mode !== 'none'}
              onChange={(on) =>
                patch(() =>
                  on
                    ? dialogs.patchFollowup(detail.id, { followup_mode: 'standard' })
                    : dialogs.patchFollowup(detail.id, { disable: true })
                )
              }
            />
          </div>

          <label className="mb-1.5 block text-[12px] text-fg-secondary">Режим</label>
          <select
            className="oai-select"
            value={detail.followup_mode || 'standard'}
            disabled={busy}
            onChange={(e) =>
              patch(() =>
                e.target.value === 'none'
                  ? dialogs.patchFollowup(detail.id, { disable: true })
                  : dialogs.patchFollowup(detail.id, { followup_mode: e.target.value })
              )
            }
          >
            {FOLLOWUP_MODES.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </section>

        {detail.awaiting_admin_quote && (
          <section className="rounded-md border border-accent/40 bg-accent/10 px-3 py-3">
            <h3 className="mb-1 text-[12px] font-semibold uppercase tracking-wide text-accent">
              ТЗ собрано — нужна цена
            </h3>
            <p className="mb-0 whitespace-pre-wrap text-[12.5px] leading-relaxed text-fg-primary">
              {detail.admin_task_summary || detail.tz_summary || 'Описание задачи пока пустое'}
            </p>
            {detail.estimated_price_usd != null && (
              <p className="mt-2 text-[12.5px] font-medium text-fg-primary">
                Черновик ИИ: ~${detail.estimated_price_usd}
                {detail.quoted_days ? ` · ~${detail.quoted_days} дн` : ''} — не финал, двигай как
                надо
              </p>
            )}
            <p className="mt-2 text-[11px] text-fg-muted">
              Summary только для тебя. Клиенту уйдёт описание продукта + цена + под ключ.
            </p>
          </section>
        )}

        <section className="border-t border-border-soft pt-4">
          <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-fg-muted">
            Цена и ТЗ
          </h3>
          {detail.estimated_price_usd != null && !detail.price_approved && (
            <p className="mb-2 text-[11.5px] text-fg-muted">
              Подсказка ИИ (черновик): ~${detail.estimated_price_usd} — можно менять
            </p>
          )}
          <label className="mb-1.5 block text-[12px] text-fg-secondary">Цена от, USD</label>
          <input
            className="oai-input mb-2 font-mono"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder={
              detail.estimated_price_usd != null ? String(detail.estimated_price_usd) : '0'
            }
          />
          <label className="mb-1.5 block text-[12px] text-fg-secondary">
            Цена до, USD (опционально)
          </label>
          <input
            className="oai-input mb-2 font-mono"
            value={priceMax}
            onChange={(e) => setPriceMax(e.target.value)}
            placeholder="850"
          />
          <label className="mb-1.5 block text-[12px] text-fg-secondary">Срок, дней</label>
          <input
            className="oai-input mb-2 font-mono"
            value={days}
            onChange={(e) => setDays(e.target.value)}
            placeholder="7"
          />
          <label className="mb-1.5 block text-[12px] text-fg-secondary">
            Текст клиенту (описание)
          </label>
          <textarea
            className="oai-textarea mb-2 !font-sans text-[12.5px]"
            rows={3}
            value={pitch}
            onChange={(e) => setPitch(e.target.value)}
            placeholder="делаем …"
          />
          <label className="mb-1.5 block text-[12px] text-fg-secondary">Summary для админа</label>
          <textarea
            className="oai-textarea mb-2 !font-sans text-[12.5px]"
            rows={3}
            value={tz}
            onChange={(e) => setTz(e.target.value)}
          />
          <div className="flex flex-col gap-2">
            <button
              type="button"
              disabled={busy}
              className="oai-btn-secondary oai-btn-sm w-full"
              onClick={() =>
                patch(() =>
                  dialogs.patchQuote(detail.id, {
                    quoted_price_usd: price === '' ? null : Number(price),
                    quoted_price_max_usd: priceMax === '' ? null : Number(priceMax),
                    quoted_days: days === '' ? null : Number(days),
                    tz_summary: tz,
                    admin_task_summary: tz,
                    client_offer_pitch: pitch,
                    price_approved: true,
                  })
                )
              }
            >
              Сохранить цену
            </button>
            <button
              type="button"
              disabled={busy || (price === '' && !detail.quoted_price_usd)}
              className="oai-btn-primary oai-btn-sm w-full"
              onClick={() =>
                patch(async () => {
                  await dialogs.patchQuote(detail.id, {
                    quoted_price_usd:
                      price === '' ? detail.quoted_price_usd : Number(price),
                    quoted_price_max_usd:
                      priceMax === '' ? detail.quoted_price_max_usd ?? null : Number(priceMax),
                    quoted_days: days === '' ? detail.quoted_days : Number(days),
                    tz_summary: tz,
                    admin_task_summary: tz,
                    client_offer_pitch: pitch,
                    price_approved: true,
                    send_offer: true,
                  });
                })
              }
            >
              Отправить цену клиенту
            </button>
          </div>
          <p className="mt-2 text-[11px] text-fg-muted">
            Клиенту: описание → цена и сроки → под ключ + 30 дней. Summary админу не уходит. После
            сохранения ИИ знает цену и ответит, если спросят.
          </p>
        </section>

        <section className="border-t border-border-soft pt-4">
          <h3 className="mb-3 text-[12px] font-semibold uppercase tracking-wide text-fg-muted">
            Финансы
          </h3>
          <div className="mb-3 grid grid-cols-2 gap-2">
            <FinTile label="Доход" value={money(finance?.income_usd)} ok />
            <FinTile label="Расход" value={money(finance?.expense_usd)} />
            <FinTile label="ИИ токены" value={money(finance?.ai_cost_usd)} />
            <FinTile
              label="Прибыль"
              value={money(finance?.profit_usd)}
              ok={(finance?.profit_usd ?? 0) >= 0}
            />
          </div>
          <p className="mb-3 text-[11px] text-fg-muted">
            Токены ИИ: {finance?.ai_tokens ?? 0} · прибыль = доход − расход − токены
          </p>

          <div className="mb-2 grid grid-cols-2 gap-2">
            <select
              className="oai-select"
              value={ledgerType}
              onChange={(e) => setLedgerType(e.target.value as 'income' | 'expense')}
            >
              <option value="income">Доход</option>
              <option value="expense">Расход</option>
            </select>
            <input
              className="oai-input font-mono"
              placeholder="Сумма $"
              value={ledgerAmount}
              onChange={(e) => setLedgerAmount(e.target.value)}
            />
          </div>
          <input
            className="oai-input mb-2"
            placeholder="Комментарий"
            value={ledgerDesc}
            onChange={(e) => setLedgerDesc(e.target.value)}
          />
          <button
            type="button"
            disabled={busy || !ledgerAmount}
            className="oai-btn-primary oai-btn-sm w-full"
            onClick={() =>
              patch(async () => {
                await bot.addLedger({
                  dialog_id: detail.id,
                  type: ledgerType,
                  amount_usd: Number(ledgerAmount),
                  description: ledgerDesc || (ledgerType === 'income' ? 'Доход' : 'Ручной расход'),
                });
                setLedgerAmount('');
                setLedgerDesc('');
              })
            }
          >
            Добавить запись
          </button>

          <ul className="mt-3 space-y-2">
            {(detail.ledger || []).slice(0, 8).map((e) => (
              <li
                key={e.id}
                className="flex items-start justify-between gap-2 border-b border-border-soft pb-2 text-[12px]"
              >
                <span className="min-w-0">
                  <span className="block font-medium">
                    {e.type === 'income' ? 'Доход' : e.type === 'refund' ? 'Возврат' : 'Расход'}
                  </span>
                  <span className="text-fg-muted">{e.description || '—'}</span>
                </span>
                <span
                  className={[
                    'shrink-0 font-mono',
                    e.type === 'income' ? 'text-accent' : 'text-fg-secondary',
                  ].join(' ')}
                >
                  {e.type === 'income' ? '+' : '−'}
                  {e.amount_usd.toFixed(2)}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="border-t border-border-soft pt-4 pb-6">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-[12px] font-semibold uppercase tracking-wide text-fg-muted">
              Сделки
            </h3>
            <Link href="/payments-admin" className="text-[11.5px] text-accent no-underline hover:underline">
              Все платежи
            </Link>
          </div>
          {(detail.orders || []).length === 0 ? (
            <p className="text-[12.5px] text-fg-tertiary">Сделок пока нет</p>
          ) : (
            <ul className="space-y-2">
              {detail.orders.map((o) => (
                <li key={o.id} className="oai-card p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[13px] font-medium">
                      ${o.amount_usdt.toFixed(2)}
                    </span>
                    <Pill
                      tone={
                        o.payment_status === 'confirmed'
                          ? 'ok'
                          : o.payment_status === 'failed' || o.payment_status === 'expired'
                            ? 'bad'
                            : 'warn'
                      }
                    >
                      {o.payment_status}
                    </Pill>
                  </div>
                  <div className="mt-1 text-[11.5px] text-fg-muted">
                    {o.payment_method} · {fmtFull(o.created_at)}
                  </div>
                  {o.description && (
                    <div className="mt-1 line-clamp-2 text-[12px] text-fg-secondary">
                      {o.description}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {(aiModal.open || aiModal.generating) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="flex max-h-[85vh] w-full max-w-lg flex-col rounded-xl border border-border bg-bg-elevated shadow-2xl">
            <div className="flex items-center justify-between border-b border-border-soft px-4 py-3">
              <div>
                <div className="text-[14px] font-semibold">Черновик ответа ИИ</div>
                {aiModal.userMessage && (
                  <div className="mt-0.5 line-clamp-1 text-[11.5px] text-fg-muted">
                    на: {aiModal.userMessage}
                  </div>
                )}
              </div>
              <button
                type="button"
                className="oai-icon-btn"
                onClick={() =>
                  setAiModal({ open: false, text: '', userMessage: '', generating: false })
                }
              >
                <IconX size={16} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-4 py-3">
              {aiModal.generating ? (
                <div className="flex items-center gap-2 py-8 text-[13px] text-fg-secondary">
                  <Spinner /> Gemini генерирует…
                </div>
              ) : (
                <textarea
                  className="oai-textarea min-h-[180px] w-full text-[13.5px] leading-relaxed"
                  value={aiModal.text}
                  onChange={(e) => setAiModal((m) => ({ ...m, text: e.target.value }))}
                />
              )}
            </div>
            <div className="flex flex-wrap gap-2 border-t border-border-soft px-4 py-3">
              <button
                type="button"
                className="oai-btn-primary"
                disabled={busy || aiModal.generating || !aiModal.text.trim()}
                onClick={sendAiDraft}
              >
                Отправить
              </button>
              <button
                type="button"
                className="oai-btn-secondary"
                disabled={aiModal.generating || !aiModal.text.trim()}
                onClick={copyAiDraft}
              >
                Копировать
              </button>
              <button
                type="button"
                className="oai-btn-secondary"
                disabled={aiModal.generating}
                onClick={openAiDraft}
              >
                Перегенерировать
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}

function KV({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[12.5px]">
      <span className="text-fg-muted">{label}</span>
      <span className={`text-right text-fg ${mono ? 'font-mono text-[11.5px]' : ''}`}>{value}</span>
    </div>
  );
}

function FinTile({
  label,
  value,
  ok,
}: {
  label: string;
  value: string;
  ok?: boolean;
}) {
  return (
    <div className="rounded-md border border-border bg-bg px-2.5 py-2">
      <div className="text-[11px] text-fg-muted">{label}</div>
      <div
        className={[
          'mt-0.5 font-mono text-[14px] font-medium',
          ok === true ? 'text-accent' : ok === false ? 'text-danger' : 'text-fg',
        ].join(' ')}
      >
        {value}
      </div>
    </div>
  );
}
