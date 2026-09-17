'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { Waterfall } from '@/components/charts';
import { IconLogs, IconRefresh } from '@/components/icons';
import { EmptyState, Segmented, Spinner, StatusDot, TopBar } from '@/components/ui/Primitives';
import { Run, RunDetail, fmtCost, fmtMs, fmtNumber, platform } from '@/lib/platform';

type Filter = 'all' | 'completed' | 'failed' | 'system';

export function LogsView({ initialId }: { initialId?: string }) {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selected, setSelected] = useState<string | null>(initialId ?? null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [loading, setLoading] = useState(false);
  const [sysLines, setSysLines] = useState<string[]>([]);
  const [sysPath, setSysPath] = useState('');

  const load = useCallback(async () => {
    const data = await platform.runs(200).catch(() => []);
    setRuns(data);
  }, []);

  const loadSys = useCallback(async () => {
    try {
      const res = await fetch('/api/logs/tail?lines=300', { cache: 'no-store' });
      if (!res.ok) return;
      const data = await res.json();
      setSysLines(data.lines || []);
      setSysPath(data.path || '');
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [load]);

  useEffect(() => {
    if (filter !== 'system') return;
    loadSys();
    const id = setInterval(loadSys, 4000);
    return () => clearInterval(id);
  }, [filter, loadSys]);

  useEffect(() => {
    if (!selected) {
      setDetail(null);
      return;
    }
    setLoading(true);
    platform
      .run(selected)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false));
  }, [selected]);

  const shown = runs.filter((r) => (filter === 'all' || filter === 'system' ? true : r.status === filter));

  return (
    <div className="flex h-screen flex-col">
      <TopBar title="Логи">
        <Segmented
          value={filter}
          onChange={setFilter}
          options={[
            { id: 'all', label: 'Все' },
            { id: 'completed', label: 'Успех' },
            { id: 'failed', label: 'Ошибки' },
            { id: 'system', label: 'Система' },
          ]}
        />
        <button
          type="button"
          onClick={() => (filter === 'system' ? loadSys() : load())}
          className="oai-icon-btn"
          title="Обновить"
        >
          <IconRefresh size={15} />
        </button>
      </TopBar>

      {filter === 'system' ? (
        <div className="oai-scroll flex-1 overflow-y-auto p-4">
          <p className="mb-2 text-[11.5px] text-fg-muted">{sysPath || 'data/logs/arix.log'}</p>
          <pre className="whitespace-pre-wrap break-all rounded-md border border-border-soft bg-bg-rail p-3 font-mono text-[11px] leading-relaxed text-fg-secondary">
            {sysLines.length ? sysLines.join('\n') : 'Лог пуст или backend не запущен'}
          </pre>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1">
          <div className="oai-scroll w-[320px] shrink-0 overflow-y-auto border-r border-border">
            {!shown.length ? (
              <EmptyState icon={<IconLogs size={22} />} title="No runs yet" />
            ) : (
              shown.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setSelected(r.id)}
                  data-selected={selected === r.id}
                  className="oai-row block w-full text-left"
                >
                  <div className="flex items-center gap-2">
                    <StatusDot status={r.status} />
                    <span className="min-w-0 flex-1 truncate text-[13px]">
                      {r.prompt_preview || r.id}
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-fg-tertiary">
                      {new Date(r.created_at).toLocaleTimeString()}
                    </span>
                  </div>
                  <div className="mt-1 flex gap-3 pl-3.5 font-mono text-[11px] text-fg-tertiary">
                    <span>{r.model_id}</span>
                    <span>{fmtMs(r.latency_ms)}</span>
                    <span>{fmtNumber(r.input_tokens + r.output_tokens)} tok</span>
                  </div>
                </button>
              ))
            )}
          </div>

          <div className="oai-scroll flex-1 overflow-y-auto">
            {loading && (
              <div className="grid h-full place-items-center text-fg-tertiary">
                <Spinner size={16} />
              </div>
            )}

            {!loading && !detail && (
              <div className="grid h-full place-items-center">
                <p className="text-[13px] text-fg-secondary">Select a log to view details.</p>
              </div>
            )}

            {!loading && detail && (
              <div className="px-6 py-5">
                <div className="mb-1 flex items-center gap-2">
                  <StatusDot status={detail.status} />
                  <h2 className="text-[15px] font-medium">{detail.model_id}</h2>
                  <span className="oai-badge">{detail.provider}</span>
                </div>
                <p className="mb-5 font-mono text-[11px] text-fg-tertiary">{detail.id}</p>

                <div className="mb-6 grid grid-cols-2 gap-x-8 gap-y-2 sm:grid-cols-3">
                  <Meta label="Status" value={detail.status} />
                  <Meta label="TTFT" value={fmtMs(detail.ttft_ms)} />
                  <Meta label="Latency" value={fmtMs(detail.latency_ms)} />
                  <Meta label="Input tokens" value={String(detail.input_tokens)} />
                  <Meta label="Output tokens" value={String(detail.output_tokens)} />
                  <Meta label="Cost" value={fmtCost(detail.cost_usd)} />
                </div>

                {detail.error && (
                  <div className="mb-6 rounded-lg border border-border bg-bg-accent px-3 py-2 text-[12px] text-fg-secondary">
                    {detail.error}
                  </div>
                )}

                <h3 className="mb-2.5 text-[13px] font-medium">Spans</h3>
                <div className="mb-6">
                  {detail.spans.length ? (
                    <Waterfall spans={detail.spans} total={detail.latency_ms} />
                  ) : (
                    <p className="text-[13px] text-fg-tertiary">No spans recorded.</p>
                  )}
                </div>

                <h3 className="mb-2 text-[13px] font-medium">Input</h3>
                <pre className="mb-5 whitespace-pre-wrap rounded-lg border border-border bg-bg-elevated p-3 font-mono text-[12px] leading-relaxed text-fg-secondary">
                  {detail.prompt_preview || '—'}
                </pre>

                <h3 className="mb-2 text-[13px] font-medium">Output</h3>
                <pre className="mb-5 whitespace-pre-wrap rounded-lg border border-border bg-bg-elevated p-3 font-mono text-[12px] leading-relaxed text-fg-secondary">
                  {detail.output_preview || '—'}
                </pre>

                <Link
                  href={`/threads/${detail.thread_id}`}
                  className="text-[13px] text-fg-secondary transition-colors hover:text-fg"
                >
                  Open thread →
                </Link>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] uppercase tracking-wide text-fg-tertiary">{label}</div>
      <div className="mt-0.5 font-mono text-[13px]">{value}</div>
    </div>
  );
}
