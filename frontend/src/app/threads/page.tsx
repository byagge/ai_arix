'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { IconPlus, IconThreads } from '@/components/icons';
import { EmptyState, TopBar, WidePage } from '@/components/ui/Primitives';
import { Thread, fmtCost, fmtNumber, platform } from '@/lib/platform';

export default function ThreadsPage() {
  const [threads, setThreads] = useState<Thread[]>([]);

  useEffect(() => {
    const load = () => platform.threads(100).then(setThreads).catch(() => undefined);
    load();
    const id = setInterval(load, 12000);
    return () => clearInterval(id);
  }, []);

  return (
    <div>
      <TopBar title="Threads">
        <Link href="/chat" className="oai-btn-primary gap-1.5">
          <IconPlus size={14} /> New thread
        </Link>
      </TopBar>

      <WidePage>
        <div className="overflow-hidden rounded-xl border border-border">
          {threads.length === 0 ? (
            <EmptyState
              icon={<IconThreads size={16} />}
              title="No threads found"
              description="A thread appears as soon as a request is executed from Chat, the API or Telegram."
              actions={
                <Link href="/chat" className="oai-btn-secondary">
                  Open Chat
                </Link>
              }
            />
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-bg-accent text-[11px] uppercase tracking-wide text-fg-tertiary">
                  <th className="px-4 py-2 text-left font-medium">Thread</th>
                  <th className="px-4 py-2 text-left font-medium">Source</th>
                  <th className="px-4 py-2 text-left font-medium">Model</th>
                  <th className="px-4 py-2 text-right font-medium">Runs</th>
                  <th className="px-4 py-2 text-right font-medium">Tokens</th>
                  <th className="px-4 py-2 text-right font-medium">Cost</th>
                  <th className="px-4 py-2 text-right font-medium">Updated</th>
                </tr>
              </thead>
              <tbody>
                {threads.map((t) => (
                  <tr key={t.id} className="border-b border-border last:border-0 hover:bg-bg-hover">
                    <td className="max-w-[280px] px-4 py-2.5">
                      <Link href={`/threads/${t.id}`} className="block truncate hover:underline">
                        {t.title || 'Untitled'}
                      </Link>
                      <span className="font-mono text-[11px] text-fg-tertiary">{t.id}</span>
                    </td>
                    <td className="px-4 py-2.5">
                      <span className="oai-badge">{t.source}</span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-fg-secondary">
                      {t.model_id ?? '—'}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px]">{t.total_runs}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px] text-fg-secondary">
                      {fmtNumber(t.total_tokens)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px] text-fg-secondary">
                      {fmtCost(t.total_cost_usd)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[11px] text-fg-tertiary">
                      {new Date(t.updated_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </WidePage>
    </div>
  );
}
