'use client';

import { useEffect, useState } from 'react';
import { IconKey } from '@/components/icons';
import { EmptyState, Notice, TopBar, WidePage } from '@/components/ui/Primitives';
import { Provider, platform } from '@/lib/platform';

const ENV_VAR: Record<string, string> = {
  openai: 'OPENAI_API_KEY',
  anthropic: 'ANTHROPIC_API_KEY',
  gemini: 'GOOGLE_API_KEY',
};

export default function ApiKeysPage() {
  const [provs, setProvs] = useState<Provider[]>([]);

  useEffect(() => {
    platform.providers().then(setProvs).catch(() => undefined);
  }, []);

  return (
    <div>
      <TopBar title="Ключи API" />

      <WidePage>
        <Notice>
          Ключи читаются из окружения backend и не попадают в браузер. Правите{' '}
          <span className="font-mono">.env</span> в корне проекта, затем перезапустите backend.
        </Notice>

        <div className="overflow-hidden rounded-xl border border-border">
          {provs.length === 0 ? (
            <EmptyState icon={<IconKey size={16} />} title="Провайдеры не найдены" />
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-bg-accent text-[11px] uppercase tracking-wide text-fg-tertiary">
                  <th className="px-4 py-2 text-left font-medium">Провайдер</th>
                  <th className="px-4 py-2 text-left font-medium">Переменная</th>
                  <th className="px-4 py-2 text-right font-medium">Модели</th>
                  <th className="px-4 py-2 text-right font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {provs.map((p) => (
                  <tr key={p.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2.5 capitalize">{p.id}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-fg-secondary">
                      {ENV_VAR[p.id] ?? '—'}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px]">{p.models}</td>
                    <td className="px-4 py-2.5 text-right">
                      <span className="oai-badge">
                        {p.configured ? 'configured' : 'missing'}
                      </span>
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
