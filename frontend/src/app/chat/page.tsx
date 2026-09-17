'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  IconChat,
  IconChevronDown,
  IconLogs,
  IconPlus,
  IconRefresh,
  IconSend,
  IconTrash,
} from '@/components/icons';
import { Row, Spinner, Toggle, TopBar } from '@/components/ui/Primitives';
import {
  ModelRecord,
  PromptTurn,
  Provider,
  Turn,
  fmtCost,
  fmtMs,
  platform,
  streamRun,
} from '@/lib/platform';

interface RunStats {
  run_id: string;
  status: string;
  latency_ms: number;
  ttft_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
  spans: { name: string; kind: string; duration_ms: number }[];
}

export default function ChatPage() {
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selected, setSelected] = useState('');
  const [systemPrompt, setSystemPrompt] = useState('');
  const [promptMsgs, setPromptMsgs] = useState<PromptTurn[]>([]);
  const [showPromptMsgs, setShowPromptMsgs] = useState(false);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState(1024);
  const [useRetrieval, setUseRetrieval] = useState(false);
  const [storeLogs, setStoreLogs] = useState(true);
  const [syncing, setSyncing] = useState(false);

  const [threadId, setThreadId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [stats, setStats] = useState<RunStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadModels = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([
        platform.models(true),
        platform.providers().catch(() => []),
      ]);
      setModels(m);
      setProviders(p);
      setSelected((prev) => {
        if (prev && m.some((x) => `${x.provider}/${x.model_id}` === prev)) return prev;
        const def = m.find((x) => x.is_default) ?? m[0];
        return def ? `${def.provider}/${def.model_id}` : '';
      });
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить модели');
    }
  }, []);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [turns, streamText]);

  const sync = async () => {
    setSyncing(true);
    setError(null);
    try {
      await platform.syncModels();
      await loadModels();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const ensureThread = useCallback(async () => {
    if (threadId) return threadId;
    const [provider, ...rest] = selected.split('/');
    const seeded = promptMsgs.filter((m) => m.content.trim());
    const created = await platform.createThread({
      provider,
      model_id: rest.join('/'),
      system_prompt: systemPrompt,
      temperature,
      max_tokens: maxTokens,
      use_retrieval: useRetrieval,
      initial_turns: seeded,
    });
    setThreadId(created.id);
    if (seeded.length) {
      setTurns(
        seeded.map((m, i) => ({
          id: i + 1,
          role: m.role,
          content: m.content,
          created_at: new Date().toISOString(),
        }))
      );
    }
    return created.id;
  }, [threadId, selected, systemPrompt, temperature, maxTokens, useRetrieval, promptMsgs]);

  const send = async () => {
    const content = draft.trim();
    if (!content || streaming || !selected) return;

    setError(null);
    setDraft('');
    setStreamText('');
    setStats(null);
    setStreaming(true);
    setDirty(false);
    setTurns((t) => [
      ...t,
      { id: Date.now(), role: 'user', content, created_at: new Date().toISOString() },
    ]);

    try {
      const id = await ensureThread();
      await platform.patchThread(id, {
        system_prompt: systemPrompt,
        temperature,
        max_tokens: maxTokens,
        use_retrieval: useRetrieval,
        provider: selected.split('/')[0],
        model_id: selected.split('/').slice(1).join('/'),
      });

      const controller = new AbortController();
      abortRef.current = controller;
      let acc = '';

      await streamRun(
        id,
        content,
        {
          onDelta: (text) => {
            acc += text;
            setStreamText(acc);
          },
          onDone: (d) => {
            setStats(d);
            setTurns((t) => [
              ...t,
              {
                id: Date.now() + 1,
                role: 'assistant',
                content: acc,
                created_at: new Date().toISOString(),
              },
            ]);
            setStreamText('');
          },
          onError: (m) => setError(m),
        },
        controller.signal
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Request failed');
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  };

  const reset = () => {
    abortRef.current?.abort();
    setThreadId(null);
    setTurns([]);
    setStreamText('');
    setStats(null);
    setError(null);
    setDirty(false);
  };

  const addPromptMsg = () => {
    setShowPromptMsgs(true);
    setPromptMsgs((m) => [...m, { role: 'user', content: '' }]);
    setDirty(true);
  };

  const noModels = models.length === 0;
  const openai = providers.find((p) => p.id === 'openai');

  return (
    <div className="flex h-full flex-col md:h-screen">
      <TopBar
        title={
          <>
            <button
              type="button"
              onClick={reset}
              className="flex items-center gap-1 rounded-md px-1 py-0.5 transition-colors hover:bg-bg-hover"
            >
              Тест чата <IconChevronDown size={12} className="text-fg-tertiary" />
            </button>
            <span className="oai-badge">Черновик</span>
            {dirty && <span className="text-[12px] text-fg-tertiary">Есть изменения</span>}
          </>
        }
      >
        <button
          type="button"
          onClick={sync}
          disabled={syncing}
          className="oai-btn-ghost gap-1.5"
          title="Синхронизировать модели с провайдерами"
        >
          {syncing ? <Spinner size={12} /> : <IconRefresh size={14} />}
          Sync
        </button>
        <Link href="/logs" className="oai-btn-ghost gap-1.5 no-underline">
          <IconLogs size={14} /> Логи
        </Link>
        <button type="button" onClick={reset} className="oai-btn-secondary gap-1.5">
          <IconPlus size={14} /> Новый
        </button>
      </TopBar>

      <div className="flex min-h-0 flex-1">
        <aside className="oai-scroll w-[300px] shrink-0 overflow-y-auto border-r border-border px-4 py-3">
          <Collapsible title="Промпт">
            <textarea
              value={systemPrompt}
              onChange={(e) => {
                setSystemPrompt(e.target.value);
                setDirty(true);
              }}
              rows={7}
              placeholder="Как должен отвечать агент: тон, инструменты, стиль"
              className="oai-textarea resize-y text-[13px] leading-relaxed"
            />
            <button
              type="button"
              onClick={addPromptMsg}
              className="mt-2 flex w-full items-center justify-between rounded-lg px-1 py-1.5 text-[13px] text-fg-secondary transition-colors hover:bg-bg-hover hover:text-fg"
            >
              Add messages to prompt
              <IconPlus size={13} />
            </button>

            {(showPromptMsgs || promptMsgs.length > 0) && (
              <div className="mt-2 space-y-2">
                {promptMsgs.map((m, i) => (
                  <div key={i} className="rounded-md border border-border bg-bg p-2">
                    <div className="mb-1.5 flex items-center gap-2">
                      <select
                        className="oai-select !h-7 flex-1"
                        value={m.role}
                        onChange={(e) => {
                          const role = e.target.value;
                          setPromptMsgs((prev) =>
                            prev.map((x, j) => (j === i ? { ...x, role } : x))
                          );
                          setDirty(true);
                        }}
                      >
                        <option value="user">user</option>
                        <option value="assistant">assistant</option>
                        <option value="system">system</option>
                      </select>
                      <button
                        type="button"
                        className="oai-icon-btn h-7 w-7"
                        onClick={() => {
                          setPromptMsgs((prev) => prev.filter((_, j) => j !== i));
                          setDirty(true);
                        }}
                      >
                        <IconTrash size={13} />
                      </button>
                    </div>
                    <textarea
                      className="oai-textarea !min-h-0 text-[12.5px]"
                      rows={3}
                      value={m.content}
                      placeholder="Пример сообщения…"
                      onChange={(e) => {
                        const content = e.target.value;
                        setPromptMsgs((prev) =>
                          prev.map((x, j) => (j === i ? { ...x, content } : x))
                        );
                        setDirty(true);
                      }}
                    />
                  </div>
                ))}
                <p className="text-[11px] text-fg-muted">
                  Эти сообщения уйдут в историю треда до первого ответа модели.
                </p>
              </div>
            )}
          </Collapsible>

          <Collapsible title="Модель">
            {openai && (
              <p className="mb-2 text-[11.5px] leading-snug text-fg-muted">
                OpenAI: {openai.configured ? 'ключ есть' : 'нет ключа'}
                {openai.endpoint ? ` · ${openai.endpoint}` : ''}
                {openai.endpoint === 'local' && (
                  <>
                    {' '}
                    — для реальных моделей очистите{' '}
                    <code className="text-fg-tertiary">OPENAI_BASE_URL</code> в .env и укажите
                    настоящий <code className="text-fg-tertiary">OPENAI_API_KEY</code>, затем Sync.
                  </>
                )}
              </p>
            )}
            <div className="space-y-1">
              <Row label="Модель">
                <select
                  value={selected}
                  onChange={(e) => {
                    setSelected(e.target.value);
                    setDirty(true);
                    setThreadId(null);
                  }}
                  className="oai-select"
                  disabled={noModels}
                >
                  {models.map((m) => (
                    <option key={m.id} value={`${m.provider}/${m.model_id}`}>
                      {m.provider}/{m.model_id}
                    </option>
                  ))}
                  {noModels && <option>нет моделей — Sync</option>}
                </select>
              </Row>
              <Row label="Temperature">
                <input
                  type="number"
                  min={0}
                  max={2}
                  step={0.05}
                  value={temperature}
                  onChange={(e) => {
                    setTemperature(Number(e.target.value));
                    setDirty(true);
                  }}
                  className="oai-select"
                />
              </Row>
              <Row label="Max tokens">
                <input
                  type="number"
                  min={1}
                  max={32000}
                  value={maxTokens}
                  onChange={(e) => {
                    setMaxTokens(Number(e.target.value));
                    setDirty(true);
                  }}
                  className="oai-select"
                />
              </Row>
              <Row label="База знаний">
                <div className="flex justify-end">
                  <Toggle
                    checked={useRetrieval}
                    onChange={(v) => {
                      setUseRetrieval(v);
                      setDirty(true);
                    }}
                  />
                </div>
              </Row>
              <Row label="Писать логи">
                <div className="flex justify-end">
                  <Toggle checked={storeLogs} onChange={setStoreLogs} />
                </div>
              </Row>
            </div>
          </Collapsible>

          {stats && (
            <Collapsible title="Last run">
              <div className="space-y-1.5 text-[12px]">
                <StatRow label="TTFT" value={fmtMs(stats.ttft_ms)} />
                <StatRow label="Latency" value={fmtMs(stats.latency_ms)} />
                <StatRow label="Input" value={String(stats.input_tokens)} />
                <StatRow label="Output" value={String(stats.output_tokens)} />
                <StatRow label="Cost" value={fmtCost(stats.cost_usd)} />
              </div>
              <Link
                href={`/logs/${stats.run_id}`}
                className="mt-2 block text-[12px] text-fg-secondary transition-colors hover:text-fg"
              >
                Trace →
              </Link>
            </Collapsible>
          )}
        </aside>

        <section className="flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="oai-scroll flex-1 overflow-y-auto">
            {turns.length === 0 && !streamText ? (
              <div className="flex h-full flex-col items-center justify-center gap-3">
                <span className="grid h-9 w-9 place-items-center rounded-lg bg-bg-accent text-fg-secondary">
                  <IconChat size={16} />
                </span>
                <p className="text-[14px] text-fg-secondary">Диалог появится здесь</p>
                {noModels && (
                  <button type="button" onClick={sync} className="oai-btn-primary mt-2">
                    Синхронизировать модели
                  </button>
                )}
              </div>
            ) : (
              <div className="mx-auto w-full max-w-[720px] space-y-6 px-6 py-8">
                {turns.map((t) => (
                  <Message key={t.id} role={t.role} content={t.content} />
                ))}
                {streamText && <Message role="assistant" content={streamText} streaming />}
                {streaming && !streamText && (
                  <div className="flex items-center gap-2 text-[13px] text-fg-tertiary">
                    <Spinner /> ждём первый токен…
                  </div>
                )}
              </div>
            )}
          </div>

          {error && (
            <div className="mx-auto mb-2 w-full max-w-[720px] px-6">
              <div className="rounded-lg border border-border bg-bg-accent px-3 py-2 text-[12px] text-fg-secondary">
                {error}
              </div>
            </div>
          )}

          <div className="px-6 pb-5">
            <div className="mx-auto w-full max-w-[720px] rounded-2xl border border-border bg-bg-input p-2.5">
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
                placeholder={noModels ? 'Сначала Sync моделей' : 'Напишите сообщение'}
                disabled={noModels}
                className="max-h-40 w-full resize-none bg-transparent px-1 py-1 text-[14px] outline-none"
              />
              <div className="flex items-center justify-between pt-1">
                <span className="px-1 text-[11px] text-fg-muted">
                  {selected || 'модель не выбрана'}
                </span>
                <button
                  type="button"
                  onClick={send}
                  disabled={streaming || !draft.trim() || noModels}
                  className="grid h-7 w-7 place-items-center rounded-full bg-fg text-bg transition-opacity disabled:opacity-30"
                >
                  {streaming ? <Spinner size={11} /> : <IconSend size={14} />}
                </button>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function Collapsible({ title, children }: { title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="mb-4 border-b border-border pb-4 last:border-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="mb-2.5 flex w-full items-center justify-between text-[13px] font-medium"
      >
        {title}
        <IconChevronDown
          size={14}
          className={`text-fg-tertiary transition-transform ${open ? '' : '-rotate-90'}`}
        />
      </button>
      {open && children}
    </div>
  );
}

function Message({
  role,
  content,
  streaming,
}: {
  role: string;
  content: string;
  streaming?: boolean;
}) {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={[
          'max-w-[85%] rounded-2xl px-3.5 py-2.5 text-[14px] leading-relaxed',
          isUser ? 'bg-fg text-bg' : 'bg-bg-accent text-fg',
        ].join(' ')}
      >
        <div className="mb-1 text-[10px] font-medium uppercase tracking-wide opacity-50">
          {role}
        </div>
        <div className="whitespace-pre-wrap break-words">
          {content}
          {streaming && <span className="ml-0.5 inline-block h-3 w-1.5 animate-blink bg-current" />}
        </div>
      </div>
    </div>
  );
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-fg-tertiary">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}
