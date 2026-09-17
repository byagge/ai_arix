'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { TelegramFormatEditor } from '@/components/TelegramFormatEditor';
import { Pill, Segmented, Spinner, Toggle } from '@/components/ui/Primitives';
import {
  BotStats,
  DialogOrder,
  LedgerEntry,
  PaymentTemplate,
  bot,
  dialogs,
} from '@/lib/bot';

type Tab = 'orders' | 'templates' | 'ledger' | 'escrow';

function fmt(iso: string | null | undefined) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusTone(s: string): 'ok' | 'warn' | 'bad' | 'default' {
  if (s === 'confirmed') return 'ok';
  if (s === 'failed' || s === 'expired') return 'bad';
  if (s === 'pending' || s === 'confirming' || s === 'draft') return 'warn';
  return 'default';
}

export default function PaymentsAdminPage() {
  const [tab, setTab] = useState<Tab>('orders');
  const [stats, setStats] = useState<BotStats | null>(null);
  const [orders, setOrders] = useState<DialogOrder[]>([]);
  const [templates, setTemplates] = useState<PaymentTemplate[]>([]);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [escrow, setEscrow] = useState<Record<string, unknown>[]>([]);
  const [orderFilter, setOrderFilter] = useState<'all' | 'pending' | 'confirmed' | 'failed'>('all');
  const [saving, setSaving] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, o, t, l, e] = await Promise.all([
        bot.stats(),
        dialogs.orders(),
        bot.templates(),
        bot.ledger(),
        dialogs.escrowDrafts().catch(() => []),
      ]);
      setStats(s);
      setOrders(o);
      setTemplates(t);
      setLedger(l);
      setEscrow(e);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  const filteredOrders = useMemo(() => {
    if (orderFilter === 'all') return orders;
    if (orderFilter === 'pending') {
      return orders.filter((o) =>
        ['pending', 'confirming', 'draft'].includes(o.payment_status)
      );
    }
    if (orderFilter === 'confirmed') {
      return orders.filter((o) => o.payment_status === 'confirmed');
    }
    return orders.filter((o) =>
      ['failed', 'expired'].includes(o.payment_status)
    );
  }, [orders, orderFilter]);

  const saveTpl = async (tpl: PaymentTemplate) => {
    setSaving(tpl.id);
    try {
      await bot.patchTemplate(tpl.id, {
        wallet_address: tpl.wallet_address,
        message_template: tpl.message_template,
        enabled: tpl.enabled,
        label: tpl.label,
      });
      await load();
    } finally {
      setSaving(null);
    }
  };

  const pendingSum = orders
    .filter((o) => ['pending', 'confirming'].includes(o.payment_status))
    .reduce((a, o) => a + o.amount_usdt, 0);

  return (
    <div className="mx-auto w-full max-w-console px-[34px] pb-20 pt-6 animate-fade-in">
      <div className="mb-1.5 flex min-h-[38px] items-center justify-between gap-4">
        <h1 className="text-[30px] font-semibold tracking-[-0.03em]">Платежи</h1>
        <button type="button" onClick={load} className="oai-btn-secondary oai-btn-sm">
          Обновить
        </button>
      </div>
      <p className="oai-lede">
        Сделки, шаблоны с Telegram-оформлением, учёт денег и эскроу-черновики.
      </p>

      {error && (
        <p className="mb-4 rounded-md border border-danger/30 bg-danger/10 px-3.5 py-2.5 text-[13px] text-[#ffa2a5]">
          {error}
        </p>
      )}

      <div className="oai-metrics mb-6" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        <Metric label="Выручка USDT" value={stats ? stats.revenue_usdt.toFixed(2) : '—'} />
        <Metric label="В ожидании" value={pendingSum.toFixed(2)} />
        <Metric
          label="Доход ledger"
          value={stats?.income_usd != null ? stats.income_usd.toFixed(2) : '—'}
        />
        <Metric
          label="Прибыль ledger"
          value={stats ? stats.ledger_usd.toFixed(2) : '—'}
        />
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-3">
        <Segmented
          value={tab}
          onChange={setTab}
          options={[
            { id: 'orders', label: 'Сделки' },
            { id: 'templates', label: 'Шаблоны' },
            { id: 'ledger', label: 'Учёт' },
            { id: 'escrow', label: 'Эскроу' },
          ]}
        />
        {loading && <Spinner size={14} />}
      </div>

      {tab === 'orders' && (
        <div>
          <div className="mb-3 flex flex-wrap gap-1.5">
            {(
              [
                ['all', 'Все'],
                ['pending', 'Ожидают'],
                ['confirmed', 'Оплачены'],
                ['failed', 'Ошибки'],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setOrderFilter(id)}
                className={[
                  'rounded-full border px-3 py-1 text-[12px] transition-colors',
                  orderFilter === id
                    ? 'border-transparent bg-bg-active text-white'
                    : 'border-border text-fg-tertiary hover:text-fg',
                ].join(' ')}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="oai-card overflow-hidden p-0">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-bg-accent text-[11px] uppercase tracking-wide text-fg-muted">
                  <th className="px-[18px] py-3 text-left font-medium">Сумма</th>
                  <th className="px-[18px] py-3 text-left font-medium">Статус</th>
                  <th className="px-[18px] py-3 text-left font-medium">Метод</th>
                  <th className="px-[18px] py-3 text-left font-medium">Клиент</th>
                  <th className="px-[18px] py-3 text-left font-medium">Описание</th>
                  <th className="px-[18px] py-3 text-right font-medium">Дата</th>
                </tr>
              </thead>
              <tbody>
                {filteredOrders.map((o) => (
                  <tr
                    key={o.id}
                    className="border-b border-border-soft last:border-0 hover:bg-white/[0.02]"
                  >
                    <td className="px-[18px] py-3 font-mono font-medium">
                      ${o.amount_usdt.toFixed(2)}
                    </td>
                    <td className="px-[18px] py-3">
                      <Pill tone={statusTone(o.payment_status)}>{o.payment_status}</Pill>
                    </td>
                    <td className="px-[18px] py-3 text-fg-secondary">{o.payment_method}</td>
                    <td className="px-[18px] py-3">
                      <Link
                        href={`/clients?id=${o.dialog_id}`}
                        className="text-accent no-underline hover:underline"
                        title="Открыть чат"
                      >
                        #{o.dialog_id}
                      </Link>
                    </td>
                    <td className="max-w-[220px] truncate px-[18px] py-3 text-fg-secondary">
                      {o.description || '—'}
                      {o.tx_hash && (
                        <span className="ml-1 font-mono text-[11px] text-fg-muted">
                          {o.tx_hash.slice(0, 10)}…
                        </span>
                      )}
                    </td>
                    <td className="px-[18px] py-3 text-right text-[12px] text-fg-muted">
                      {fmt(o.paid_at || o.created_at)}
                    </td>
                  </tr>
                ))}
                {filteredOrders.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-[18px] py-12 text-center text-fg-tertiary"
                    >
                      Сделок нет
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'templates' && (
        <div>
          <p className="mb-4 text-[13px] text-fg-tertiary">
            Сети USDT: TRC-20, BEP-20, ERC-20, Solana, TON, Polygon, Arbitrum, Optimism, Avalanche +
            native TON. Текст — Telegram HTML (жирный, курсив, цитата, код с клик-копией). Premium
            emoji вставляйте из Telegram как есть.
          </p>
          <div className="grid gap-4 lg:grid-cols-2">
            {templates.map((tpl) => (
              <div key={tpl.id} className="oai-card p-5">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <input
                      className="w-full bg-transparent text-[14px] font-semibold outline-none"
                      value={tpl.label}
                      onChange={(e) =>
                        setTemplates((prev) =>
                          prev.map((t) =>
                            t.id === tpl.id ? { ...t, label: e.target.value } : t
                          )
                        )
                      }
                    />
                    <div className="mt-0.5">
                      <span className="oai-badge">{tpl.network_key}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-fg-muted">Вкл</span>
                    <Toggle
                      checked={tpl.enabled}
                      onChange={(v) =>
                        setTemplates((prev) =>
                          prev.map((t) => (t.id === tpl.id ? { ...t, enabled: v } : t))
                        )
                      }
                    />
                  </div>
                </div>

                <label className="mb-1.5 block text-[12.5px] font-medium text-fg-secondary">
                  Адрес кошелька
                </label>
                <input
                  className="oai-input mb-3 font-mono text-[12.5px]"
                  value={tpl.wallet_address}
                  onChange={(e) =>
                    setTemplates((prev) =>
                      prev.map((t) =>
                        t.id === tpl.id ? { ...t, wallet_address: e.target.value } : t
                      )
                    )
                  }
                  placeholder="Адрес для этой сети"
                />

                <label className="mb-1.5 block text-[12.5px] font-medium text-fg-secondary">
                  Текст сообщения
                </label>
                <TelegramFormatEditor
                  value={tpl.message_template}
                  onChange={(message_template) =>
                    setTemplates((prev) =>
                      prev.map((t) => (t.id === tpl.id ? { ...t, message_template } : t))
                    )
                  }
                  rows={7}
                />

                <button
                  type="button"
                  onClick={() => saveTpl(tpl)}
                  disabled={saving === tpl.id}
                  className="oai-btn-primary mt-4"
                >
                  {saving === tpl.id ? '…' : 'Сохранить'}
                </button>
              </div>
            ))}
            {templates.length === 0 && (
              <div className="oai-card col-span-full px-5 py-12 text-center text-[13px] text-fg-tertiary">
                Шаблоны ещё не созданы — перезапустите backend (seed при старте)
              </div>
            )}
          </div>
        </div>
      )}

      {tab === 'ledger' && (
        <div>
          <p className="mb-4 text-[13px] text-fg-tertiary">
            <b className="font-medium text-fg-secondary">Учёт</b> — журнал доходов и расходов
            (автоматически с оплат + вручную из карточки клиента). Прибыль = доход − расход.
          </p>
          <div className="oai-card overflow-hidden p-0">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-border bg-bg-accent text-[11px] uppercase tracking-wide text-fg-muted">
                <th className="px-[18px] py-3 text-left font-medium">Тип</th>
                <th className="px-[18px] py-3 text-left font-medium">Сумма</th>
                <th className="px-[18px] py-3 text-left font-medium">Клиент</th>
                <th className="px-[18px] py-3 text-left font-medium">Описание</th>
                <th className="px-[18px] py-3 text-right font-medium">Дата</th>
              </tr>
            </thead>
            <tbody>
              {ledger.map((e) => (
                <tr
                  key={e.id}
                  className="border-b border-border-soft last:border-0 hover:bg-white/[0.02]"
                >
                  <td className="px-[18px] py-3">
                    <Pill tone={e.type === 'income' ? 'ok' : e.type === 'refund' ? 'warn' : 'default'}>
                      {e.type === 'income' ? 'доход' : e.type === 'refund' ? 'возврат' : 'расход'}
                    </Pill>
                  </td>
                  <td
                    className={[
                      'px-[18px] py-3 font-mono font-medium',
                      e.type === 'income' ? 'text-accent' : '',
                    ].join(' ')}
                  >
                    {e.type === 'income' ? '+' : '−'}
                    {e.amount_usd.toFixed(2)} {e.currency}
                  </td>
                  <td className="px-[18px] py-3 text-fg-secondary">
                    {e.dialog_id != null ? `#${e.dialog_id}` : '—'}
                  </td>
                  <td className="max-w-[280px] truncate px-[18px] py-3 text-fg-secondary">
                    {e.description || '—'}
                    {e.tx_hash && (
                      <span className="ml-1 font-mono text-[11px] text-fg-muted">
                        {e.tx_hash.slice(0, 12)}…
                      </span>
                    )}
                  </td>
                  <td className="px-[18px] py-3 text-right text-[12px] text-fg-muted">
                    {fmt(e.created_at)}
                  </td>
                </tr>
              ))}
              {ledger.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-[18px] py-12 text-center text-fg-tertiary">
                    Записей нет — добавляйте доход/расход в карточке клиента
                  </td>
                </tr>
              )}
            </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'escrow' && (
        <div>
          <p className="mb-4 text-[13px] text-fg-tertiary">
            <b className="font-medium text-fg-secondary">Эскроу</b> — черновики безопасных сделок
            (деньги через посредника). Создаются агентом, подтверждает админ — без авто-создания.
          </p>
          <div className="space-y-3">
          {escrow.map((d, i) => (
            <div key={String(d.id ?? i)} className="oai-card p-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-mono text-[14px] font-medium">
                  ${Number(d.amount_usdt ?? 0).toFixed(2)}
                </div>
                <Pill tone="warn">{String(d.status || 'draft')}</Pill>
              </div>
              <div className="mt-2 grid gap-1 text-[12.5px] text-fg-secondary sm:grid-cols-2">
                <div>
                  Клиент:{' '}
                  <Link
                    href={`/clients?id=${d.dialog_id}`}
                    className="text-accent no-underline hover:underline"
                  >
                    #{String(d.dialog_id ?? '—')}
                  </Link>
                </div>
                <div>Draft: {String(d.draft_id || '—')}</div>
                <div className="sm:col-span-2">{String(d.description || d.notes || '—')}</div>
                <div className="text-fg-muted">{fmt(String(d.created_at || ''))}</div>
              </div>
            </div>
          ))}
          {escrow.length === 0 && (
            <div className="oai-card px-5 py-12 text-center text-[13px] text-fg-tertiary">
              Черновиков эскроу нет
            </div>
          )}
          </div>
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="oai-metric !min-h-[88px]">
      <div className="text-[12.5px] text-fg-tertiary">{label}</div>
      <div className="mt-1.5 font-mono text-[21px] font-medium tracking-[-0.02em]">{value}</div>
    </div>
  );
}
