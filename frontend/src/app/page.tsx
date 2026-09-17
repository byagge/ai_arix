'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { BarSeries, Sparkline } from '@/components/charts';
import {
  IconArrowRight,
  IconCard,
  IconChat,
  IconCheck,
  IconKey,
  IconModel,
  IconStorage,
  IconThreads,
  IconX,
} from '@/components/icons';
import {
  MetricCell,
  Page,
  PageTitle,
  Pill,
  Section,
  Segmented,
} from '@/components/ui/Primitives';
import { BotStats, bot } from '@/lib/bot';
import {
  Metrics,
  ModelRecord,
  Provider,
  UsageBucket,
  fmtCost,
  fmtNumber,
  platform,
} from '@/lib/platform';

const RANGES = [
  { id: '24h', label: '24ч', hours: 24 },
  { id: '7d', label: '7д', hours: 168 },
  { id: '14d', label: '14д', hours: 336 },
  { id: '30d', label: '30д', hours: 720 },
] as const;

type RangeId = (typeof RANGES)[number]['id'];

export default function HomePage() {
  const [range, setRange] = useState<RangeId>('7d');
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [series, setSeries] = useState<UsageBucket[]>([]);
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [provs, setProvs] = useState<Provider[]>([]);
  const [botStats, setBotStats] = useState<BotStats | null>(null);
  const [dismissed, setDismissed] = useState(false);

  const hours = RANGES.find((r) => r.id === range)!.hours;

  const load = useCallback(async () => {
    const [m, s, mo, p, bs] = await Promise.all([
      platform.metrics(hours).catch(() => null),
      platform.usageSeries(hours, 24).catch(() => null),
      platform.models(true).catch(() => []),
      platform.providers().catch(() => []),
      bot.stats().catch(() => null),
    ]);
    if (m) setMetrics(m);
    if (s) setSeries(s.series);
    setModels(mo);
    setProvs(p);
    if (bs) setBotStats(bs);
  }, [hours]);

  useEffect(() => {
    load();
    const id = setInterval(load, 15000);
    return () => clearInterval(id);
  }, [load]);

  const hasKey = provs.some((p) => p.configured);
  const hasModels = models.length > 0;
  const hasClients = (botStats?.dialogs ?? 0) > 0;

  const steps = [
    { label: 'Подключите ключ провайдера', done: hasKey, href: '/api-keys', Icon: IconKey },
    { label: 'Выберите модель по умолчанию', done: hasModels, href: '/models', Icon: IconModel },
    { label: 'Загрузите базу знаний', done: false, href: '/storage', Icon: IconStorage },
  ];

  return (
    <Page>
      <PageTitle
        lede="Управление ИИ-сотрудником: клиенты, оплаты и поведение агента."
        actions={
          <Segmented
            value={range}
            onChange={setRange}
            options={RANGES.map((r) => ({ id: r.id, label: r.label }))}
          />
        }
      >
        Главная
      </PageTitle>

      {!dismissed && (
        <section className="mb-6">
          <div className="mb-2.5 flex items-center justify-between">
            <h2 className="text-[15px] font-semibold">С чего начать</h2>
            <button
              type="button"
              onClick={() => setDismissed(true)}
              className="flex items-center gap-1 rounded-sm px-1.5 py-1 text-[12.5px] text-fg-tertiary transition-colors hover:bg-bg-hover hover:text-fg"
            >
              <IconX size={13} /> Скрыть
            </button>
          </div>

          <div className="oai-getstarted">
            <ol className="flex flex-col gap-1 px-5 py-[18px]">
              {steps.map((s, i) => (
                <li key={s.label}>
                  <Link
                    href={s.href}
                    className="flex items-center gap-2.5 rounded-sm py-1.5 text-[13.5px] text-fg transition-colors hover:text-fg no-underline"
                  >
                    <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border border-border bg-bg-accent text-fg-secondary">
                      {s.done ? (
                        <IconCheck size={14} className="text-accent" />
                      ) : (
                        <s.Icon size={14} />
                      )}
                    </span>
                    <span className={s.done ? 'text-fg-muted line-through' : ''}>
                      {i + 1}. {s.label}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>

            <div className="oai-gs-art">
              <div className="grid w-full grid-cols-2 gap-2.5">
                <Link href="/clients" className="oai-gs-card no-underline">
                  <strong className="flex items-center gap-1 text-[12.5px] font-semibold">
                    Клиенты <IconArrowRight size={12} />
                  </strong>
                  <span className="mt-1 block text-[11.5px] leading-snug text-fg-tertiary">
                    Диалоги и статусы воронки
                  </span>
                </Link>
                <Link href="/chat" className="oai-gs-card no-underline">
                  <strong className="flex items-center gap-1 text-[12.5px] font-semibold">
                    Тест чата <IconArrowRight size={12} />
                  </strong>
                  <span className="mt-1 block text-[11.5px] leading-snug text-fg-tertiary">
                    Проверить ответы модели
                  </span>
                </Link>
              </div>
            </div>
          </div>
        </section>
      )}

      <div className="oai-metrics mb-6">
        <MetricCell label="Диалоги" value={botStats?.dialogs ?? '—'} href={false}>
          <div className="text-[12px] text-fg-muted">
            {botStats ? `${botStats.in_progress} в работе` : 'Бот не отвечает'}
          </div>
        </MetricCell>
        <MetricCell label="Ждут оплату" value={botStats?.payment_pending ?? '—'} href={false}>
          <div className="text-[12px] text-fg-muted">
            {botStats ? `${botStats.revenue_usdt.toFixed(2)} USDT выручка` : '—'}
          </div>
        </MetricCell>
        <MetricCell
          label="Успех ранов"
          value={
            metrics?.success_rate != null
              ? `${(metrics.success_rate * 100).toFixed(0)}%`
              : '—'
          }
          href={false}
        >
          <div className="text-[12px] text-fg-muted">
            {metrics ? `${metrics.failed} ошибок · ${metrics.runs} ранов` : '—'}
          </div>
        </MetricCell>
        <MetricCell label="Запросы" value={metrics?.runs ?? 0}>
          <BarSeries data={series.slice(-8).map((s) => s.requests)} />
        </MetricCell>
        <MetricCell
          label="Токены"
          value={fmtNumber(metrics ? metrics.input_tokens + metrics.output_tokens : 0)}
        >
          <div className="text-fg">
            <Sparkline data={series.map((s) => s.input_tokens + s.output_tokens)} />
          </div>
        </MetricCell>
        <MetricCell label="Расход" value={fmtCost(metrics?.cost_usd ?? 0)} href={false}>
          <div className="text-[12px] text-fg-muted">
            p95 {metrics ? `${metrics.latency_p95_ms} мс` : '—'}
          </div>
        </MetricCell>
      </div>

      <div className="mt-7 grid gap-6 lg:grid-cols-[1.25fr_1fr]">
        <div>
          <h2 className="mb-2.5 text-[15px] font-semibold">Статус агента</h2>
          <div className="oai-card p-5">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <Pill tone={hasKey ? 'ok' : 'warn'}>
                {hasKey ? 'Ключи подключены' : 'Нет ключей'}
              </Pill>
              <Pill tone={hasModels ? 'ok' : 'warn'}>
                {hasModels ? `${models.length} моделей` : 'Нет моделей'}
              </Pill>
              <Pill tone={hasClients ? 'ok' : 'default'}>
                {hasClients ? 'Есть клиенты' : 'Клиентов пока нет'}
              </Pill>
            </div>
            <p className="mb-4 text-[13px] text-fg-tertiary">
              Агент ведёт продажи в Telegram: квалификация, оффер, оплата и follow-up.
              Здесь — только управление.
            </p>
            <div className="flex flex-wrap gap-2">
              <Link href="/clients" className="oai-btn-primary no-underline">
                <IconThreads size={14} /> Клиенты
              </Link>
              <Link href="/payments-admin" className="oai-btn-secondary no-underline">
                <IconCard size={14} /> Платежи
              </Link>
              <Link href="/settings" className="oai-btn-ghost no-underline">
                Настройки
              </Link>
            </div>
          </div>
        </div>

        <Section title="Активность">
          <ul className="m-0 list-none space-y-0 p-0">
            {(metrics?.by_model ?? []).slice(0, 5).map((m) => (
              <li
                key={`${m.provider}/${m.model_id}`}
                className="flex gap-2.5 border-b border-border-soft py-2.5 last:border-0"
              >
                <span className="mt-0.5 grid h-[26px] w-[26px] shrink-0 place-items-center rounded-sm border border-border bg-bg-accent text-fg-tertiary">
                  <IconModel size={12} />
                </span>
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium">{m.model_id}</div>
                  <div className="text-[12px] text-fg-muted">
                    {m.runs} запросов · {fmtNumber(m.tokens)} ток. · {m.avg_latency_ms} мс
                  </div>
                </div>
              </li>
            ))}
            {!metrics?.by_model?.length && (
              <li className="py-3 text-[13px] text-fg-tertiary">
                Пока нет запросов за выбранный период.
                <Link href="/chat" className="ml-1 inline-flex items-center gap-0.5">
                  Тест чата <IconChat size={12} />
                </Link>
              </li>
            )}
          </ul>
        </Section>
      </div>
    </Page>
  );
}
