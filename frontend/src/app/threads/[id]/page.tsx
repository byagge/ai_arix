'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { EmptyState, Notice, TopBar, WidePage } from '@/components/ui/Primitives';
import { ThreadDetail, fmtCost, fmtNumber, platform } from '@/lib/platform';

export default function ThreadDetailPage() {
  const params = useParams<{ id: string }>();
  const [thread, setThread] = useState<ThreadDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!params?.id) return;
    platform
      .thread(params.id)
      .then(setThread)
      .catch((e) => setError(e.message));
  }, [params?.id]);

  return (
    <div>
      <TopBar title={thread?.title || 'Thread'}>
        <Link href="/threads" className="oai-btn-secondary">
          Back
        </Link>
      </TopBar>

      <WidePage>
        {error && <Notice>{error}</Notice>}
        {!thread && !error && <p className="text-[13px] text-fg-secondary">Loading…</p>}

        {thread && (
          <>
            <div className="mb-6 grid gap-3 sm:grid-cols-4">
              <Tile label="Runs" value={String(thread.total_runs)} />
              <Tile label="Tokens" value={fmtNumber(thread.total_tokens)} />
              <Tile label="Cost" value={fmtCost(thread.total_cost_usd)} />
              <Tile label="Model" value={thread.model_id ?? '—'} />
            </div>

            {thread.system_prompt && (
              <div className="oai-card mb-6 p-4">
                <div className="mb-2 text-[11px] uppercase tracking-wide text-fg-tertiary">
                  System prompt
                </div>
                <pre className="whitespace-pre-wrap font-mono text-[12px] text-fg-secondary">
                  {thread.system_prompt}
                </pre>
              </div>
            )}

            <div className="overflow-hidden rounded-xl border border-border">
              {thread.turns.length === 0 ? (
                <EmptyState title="No messages in this thread" />
              ) : (
                thread.turns.map((t) => (
                  <div key={t.id} className="border-b border-border px-5 py-4 last:border-0">
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-[11px] uppercase tracking-wide text-fg-tertiary">
                        {t.role}
                      </span>
                      <span className="font-mono text-[11px] text-fg-tertiary">
                        {new Date(t.created_at).toLocaleString()}
                      </span>
                    </div>
                    <div className="whitespace-pre-wrap text-[14px] leading-relaxed">
                      {t.content}
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </WidePage>
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="oai-card p-4">
      <div className="text-[13px] text-fg-secondary">{label}</div>
      <div className="mt-1 truncate text-[16px] font-medium">{value}</div>
    </div>
  );
}
