'use client';

import { useCallback, useEffect, useState } from 'react';
import { IconExternal } from '@/components/icons';
import {
  Field,
  Notice,
  Tabs,
  Toggle,
  TopBar,
  WidePage,
} from '@/components/ui/Primitives';
import { telegram, TelegramStatus } from '@/lib/bot';
import { ModelRecord, Provider, platform } from '@/lib/platform';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

type TabId = 'telegram' | 'general' | 'limits' | 'agent' | 'providers';

interface AgentSettings {
  orchestrator_prompt: string;
  sales_prompt: string;
  followup_prompt: string;
  payment_prompt: string;
  tone: string;
  autonomy_level: number;
  max_followups: number;
  discount_max_percent: number;
}

export default function SettingsPage() {
  const [tab, setTab] = useState<TabId>('telegram');
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [provs, setProvs] = useState<Provider[]>([]);
  const [agent, setAgent] = useState<AgentSettings | null>(null);
  const [tg, setTg] = useState<TelegramStatus | null>(null);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [testMsg, setTestMsg] = useState<string | null>(null);
  const [disableUserKeys, setDisableUserKeys] = useState(false);

  const load = useCallback(async () => {
    const [m, p, t] = await Promise.all([
      platform.models().catch(() => []),
      platform.providers().catch(() => []),
      telegram.status().catch(() => null),
    ]);
    setModels(m);
    setProvs(p);
    setTg(t);
    fetch(`${BASE}/api/settings`, { cache: 'no-store' })
      .then((r) => r.json())
      .then(setAgent)
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (!agent) return;
    try {
      const res = await fetch(`${BASE}/api/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(agent),
      });
      if (!res.ok) throw new Error(`Save failed: ${res.status}`);
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    }
  };

  const saveRuntime = async (patch: Partial<TelegramStatus['runtime']>) => {
    setBusy(true);
    setError(null);
    try {
      const runtime = await telegram.patchRuntime(patch);
      setTg((prev) => (prev ? { ...prev, runtime } : prev));
      setSaved(true);
      setTimeout(() => setSaved(false), 1800);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка сохранения');
    } finally {
      setBusy(false);
    }
  };

  const refreshTg = async () => {
    setBusy(true);
    setError(null);
    try {
      setTg(await telegram.refresh());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Ошибка обновления');
    } finally {
      setBusy(false);
    }
  };

  const runTestSend = async () => {
    setBusy(true);
    setTestMsg(null);
    try {
      const r = await telegram.testSend();
      setTestMsg(
        r.ok
          ? `Отправлено → ${r.target}`
          : `Не отправлено: ${r.error || 'ошибка'}. ${r.hint || ''}`
      );
      await refreshTg();
    } catch (e) {
      setTestMsg(e instanceof Error ? e.message : 'Ошибка теста');
    } finally {
      setBusy(false);
    }
  };

  const defaultModel = models.find((m) => m.is_default);
  const rt = tg?.runtime;

  return (
    <div>
      <TopBar title="Настройки">
        <a
          href={`${BASE}/docs`}
          target="_blank"
          rel="noreferrer"
          className="oai-btn-secondary gap-1.5 no-underline"
        >
          API docs <IconExternal size={12} />
        </a>
      </TopBar>

      <WidePage>
        <div className="mb-6">
          <Tabs
            value={tab}
            onChange={setTab}
            options={[
              { id: 'telegram', label: 'Telegram' },
              { id: 'general', label: 'Общее' },
              { id: 'limits', label: 'Лимиты' },
              { id: 'agent', label: 'Агент' },
              { id: 'providers', label: 'Провайдеры' },
            ]}
          />
        </div>

        {error && <Notice>{error}</Notice>}

        {tab === 'telegram' && (
          <div className="max-w-[720px]">
            {tg?.blocked_by_can_reply && (
              <Notice>
                <strong>ИИ не может отвечать:</strong> у Business-бота{' '}
                <code>can_reply=false</code>. {tg.howto_fix_reply}
              </Notice>
            )}

            <div className="mb-5 grid gap-3 sm:grid-cols-3">
              <StatusCard
                label="Токен"
                ok={!!tg?.token_set}
                value={tg?.token_set ? 'задан' : 'нет в .env'}
              />
              <StatusCard
                label="Polling"
                ok={!!tg?.running}
                value={tg?.running ? 'работает' : 'выключен'}
              />
              <StatusCard
                label="Admin ID"
                ok={!!tg?.admin_id}
                value={tg?.admin_id ? String(tg.admin_id) : 'не задан'}
              />
            </div>

            <div className="mb-5 flex flex-wrap gap-2">
              <button type="button" className="oai-btn-secondary" disabled={busy} onClick={refreshTg}>
                Обновить статус
              </button>
              <button type="button" className="oai-btn-secondary" disabled={busy} onClick={runTestSend}>
                Тест отправки
              </button>
            </div>
            {testMsg && <p className="mb-4 text-[13px] text-fg-secondary">{testMsg}</p>}

            <h3 className="mb-2 text-[13px] font-semibold">Business-подключения</h3>
            {(tg?.connections?.length ?? 0) === 0 ? (
              <p className="mb-5 text-[13px] text-fg-muted">
                Пока нет. Подключите бота в Telegram → Business → Чат-боты.
              </p>
            ) : (
              <div className="mb-6 space-y-2">
                {tg!.connections.map((c) => {
                  const can =
                    c.live_can_reply ?? c.can_reply;
                  const en = c.live_is_enabled ?? c.is_enabled;
                  return (
                    <div
                      key={c.connection_id}
                      className="rounded-lg border border-border bg-bg-elevated px-4 py-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <div className="text-[13px] font-medium">
                          owner {c.owner_id}
                          <span className="ml-2 font-mono text-[11px] text-fg-muted">
                            {c.connection_id.slice(0, 16)}…
                          </span>
                        </div>
                        <div className="flex gap-1.5">
                          <span className={`oai-badge ${en ? 'oai-badge-ok' : 'oai-badge-warn'}`}>
                            {en ? 'вкл' : 'выкл'}
                          </span>
                          <span className={`oai-badge ${can ? 'oai-badge-ok' : 'oai-badge-warn'}`}>
                            {can ? 'can_reply' : 'нет reply'}
                          </span>
                        </div>
                      </div>
                      {c.block_reason === 'can_reply_false' && (
                        <p className="mt-2 text-[12px] text-fg-secondary">{tg!.howto_fix_reply}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {rt && (
              <>
                <h3 className="mb-3 text-[13px] font-semibold">Управление ИИ</h3>
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[13px] font-medium">Глобальный ИИ</div>
                    <div className="text-[11.5px] text-fg-muted">Выкл — только сохранение / оператор</div>
                  </div>
                  <Toggle
                    checked={rt.global_ai_enabled}
                    onChange={(v) => saveRuntime({ global_ai_enabled: v })}
                  />
                </div>
                <div className="mb-5 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[13px] font-medium">Форсировать ответы Business</div>
                    <div className="text-[11.5px] text-fg-muted">
                      Пробовать отвечать даже при can_reply=false (Telegram может отклонить)
                    </div>
                  </div>
                  <Toggle
                    checked={rt.force_business_reply}
                    onChange={(v) => saveRuntime({ force_business_reply: v })}
                  />
                </div>
                <Field label="Задержка ответа min (сек)">
                  <input
                    type="number"
                    className="oai-input"
                    value={rt.reply_delay_min_sec}
                    onChange={(e) =>
                      setTg((prev) =>
                        prev
                          ? {
                              ...prev,
                              runtime: {
                                ...prev.runtime,
                                reply_delay_min_sec: Number(e.target.value),
                              },
                            }
                          : prev
                      )
                    }
                  />
                </Field>
                <Field label="Задержка ответа max (сек)">
                  <input
                    type="number"
                    className="oai-input"
                    value={rt.reply_delay_max_sec}
                    onChange={(e) =>
                      setTg((prev) =>
                        prev
                          ? {
                              ...prev,
                              runtime: {
                                ...prev.runtime,
                                reply_delay_max_sec: Number(e.target.value),
                              },
                            }
                          : prev
                      )
                    }
                  />
                </Field>
                <button
                  type="button"
                  className="oai-btn-primary"
                  disabled={busy || !rt}
                  onClick={() =>
                    saveRuntime({
                      reply_delay_min_sec: rt.reply_delay_min_sec,
                      reply_delay_max_sec: rt.reply_delay_max_sec,
                    })
                  }
                >
                  {saved ? 'Сохранено' : 'Сохранить задержки'}
                </button>
              </>
            )}
          </div>
        )}

        {tab === 'general' && (
          <div className="max-w-[560px]">
            <Field label="Имя проекта">
              <input className="oai-input" defaultValue="Arix" />
            </Field>

            <Field label="Модель по умолчанию">
              <select
                className="oai-input cursor-pointer"
                value={defaultModel?.id ?? ''}
                onChange={async (e) => {
                  await platform.makeDefault(Number(e.target.value));
                  load();
                }}
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.provider} / {m.model_id}
                  </option>
                ))}
                {models.length === 0 && <option value="">нет моделей</option>}
              </select>
            </Field>

            <Field label="База данных" hint="Задаётся через DATABASE_URL в .env">
              <input className="oai-input" value="sqlite · data/ai_agent.db" readOnly />
            </Field>

            <div className="mb-5">
              <p className="mb-1.5 text-[13px] font-medium">Провайдеры</p>
              {provs.map((p) => (
                <label
                  key={p.id}
                  className="mb-1.5 flex items-center gap-2 text-[13px] capitalize"
                >
                  <input
                    type="checkbox"
                    checked={p.configured}
                    readOnly
                    className="h-3.5 w-3.5 accent-[var(--accent)]"
                  />
                  {p.id}
                  <span className="text-[12px] text-fg-tertiary">({p.models} моделей)</span>
                </label>
              ))}
            </div>

            <div className="mb-6">
              <p className="mb-1.5 text-[13px] font-medium">Доступ</p>
              <Toggle checked={disableUserKeys} onChange={setDisableUserKeys} />
            </div>

            <button type="button" onClick={save} className="oai-btn-primary">
              {saved ? 'Сохранено' : 'Сохранить'}
            </button>
          </div>
        )}

        {tab === 'limits' && agent && (
          <div className="max-w-[560px]">
            <Field label="Макс. follow-up" hint="Проактивных сообщений на диалог Telegram">
              <input
                type="number"
                className="oai-input"
                value={agent.max_followups}
                onChange={(e) => setAgent({ ...agent, max_followups: Number(e.target.value) })}
              />
            </Field>
            <Field label="Макс. скидка, %">
              <input
                type="number"
                className="oai-input"
                value={agent.discount_max_percent}
                onChange={(e) =>
                  setAgent({ ...agent, discount_max_percent: Number(e.target.value) })
                }
              />
            </Field>
            <Field label={`Автономность · ${agent.autonomy_level}`}>
              <input
                type="range"
                min={1}
                max={10}
                value={agent.autonomy_level}
                onChange={(e) => setAgent({ ...agent, autonomy_level: Number(e.target.value) })}
                className="w-full accent-[var(--accent)]"
              />
            </Field>
            <button type="button" onClick={save} className="oai-btn-primary">
              {saved ? 'Сохранено' : 'Сохранить'}
            </button>
          </div>
        )}

        {tab === 'agent' && agent && (
          <div className="max-w-[720px]">
            <Field label="Тон">
              <select
                className="oai-input cursor-pointer"
                value={agent.tone}
                onChange={(e) => setAgent({ ...agent, tone: e.target.value })}
              >
                <option value="professional_friendly">Деловой дружелюбный</option>
                <option value="casual">Неформальный</option>
                <option value="formal">Формальный</option>
                <option value="persuasive">Убеждающий</option>
              </select>
            </Field>

            {(
              [
                ['orchestrator_prompt', 'Оркестратор'],
                ['sales_prompt', 'Продажи'],
                ['followup_prompt', 'Follow-up'],
                ['payment_prompt', 'Оплата'],
              ] as const
            ).map(([key, label]) => (
              <div key={key} className="mb-5">
                <label className="mb-1.5 block text-[12.5px] font-medium text-fg-secondary">
                  {label}
                </label>
                <textarea
                  value={agent[key]}
                  onChange={(e) => setAgent({ ...agent, [key]: e.target.value })}
                  rows={5}
                  className="oai-textarea text-[12px] leading-relaxed"
                />
              </div>
            ))}

            <button type="button" onClick={save} className="oai-btn-primary">
              {saved ? 'Сохранено' : 'Сохранить'}
            </button>
          </div>
        )}

        {tab === 'providers' && (
          <div className="max-w-[560px]">
            <Notice>
              Ключи хранятся в окружении backend. Пропишите в{' '}
              <span className="font-mono">.env</span> и перезапустите сервер.
            </Notice>
            {provs.map((p) => (
              <div
                key={p.id}
                className="mb-2 flex items-center justify-between rounded-lg border border-border bg-bg-elevated px-4 py-3"
              >
                <div>
                  <div className="text-[13px] font-medium capitalize">{p.id}</div>
                  <div className="text-[12px] text-fg-secondary">{p.models} моделей</div>
                </div>
                <span className={`oai-badge ${p.configured ? 'oai-badge-ok' : 'oai-badge-warn'}`}>
                  {p.configured ? 'ок' : 'нет ключа'}
                </span>
              </div>
            ))}
          </div>
        )}
      </WidePage>
    </div>
  );
}

function StatusCard({ label, ok, value }: { label: string; ok: boolean; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-bg-elevated px-3 py-3">
      <div className="text-[11px] uppercase tracking-wide text-fg-muted">{label}</div>
      <div className={`mt-1 text-[13px] font-medium ${ok ? 'text-fg' : 'text-amber-400'}`}>
        {value}
      </div>
    </div>
  );
}
