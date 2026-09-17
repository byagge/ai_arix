'use client';

import { useCallback, useEffect, useState } from 'react';
import { IconModel, IconRefresh } from '@/components/icons';
import {
  EmptyState,
  Notice,
  Spinner,
  StatusDot,
  TopBar,
  WidePage,
} from '@/components/ui/Primitives';
import { ModelRecord, Provider, fmtMs, platform } from '@/lib/platform';

export default function ModelsPage() {
  const [models, setModels] = useState<ModelRecord[]>([]);
  const [provs, setProvs] = useState<Provider[]>([]);
  const [syncing, setSyncing] = useState(false);
  const [checking, setChecking] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [m, p] = await Promise.all([
      platform.models().catch(() => []),
      platform.providers().catch(() => []),
    ]);
    setModels(m);
    setProvs(p);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const sync = async () => {
    setSyncing(true);
    setNotice(null);
    try {
      const res = await platform.syncModels();
      setNotice(
        res.results
          .map((r) => {
            const x = r as Record<string, unknown>;
            return `${x.provider}: ${x.error ?? x.skipped ?? `${x.discovered} models`}`;
          })
          .join('  ·  ')
      );
      await load();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'Sync failed');
    } finally {
      setSyncing(false);
    }
  };

  const check = async (id: number) => {
    setChecking(id);
    try {
      const updated = await platform.checkModel(id);
      setModels((prev) => prev.map((m) => (m.id === id ? updated : m)));
    } finally {
      setChecking(null);
    }
  };

  const toggle = async (m: ModelRecord) => {
    const updated = await platform.patchModel(m.id, { enabled: !m.enabled });
    setModels((prev) => prev.map((x) => (x.id === m.id ? updated : x)));
  };

  return (
    <div>
      <TopBar title="Модели">
        <button type="button" onClick={sync} disabled={syncing} className="oai-btn-primary gap-1.5">
          {syncing ? <Spinner size={12} /> : <IconRefresh size={14} />}
          Синхронизация
        </button>
      </TopBar>

      <WidePage>
        {notice && <Notice>{notice}</Notice>}

        {provs.some((p) => p.id === 'openai' && p.endpoint === 'local') && (
          <Notice tone="warn">
            OpenAI сейчас смотрит на <span className="font-mono">local</span> endpoint (
            OPENAI_BASE_URL). Чтобы подтянуть реальные модели: в{' '}
            <span className="font-mono">.env</span> поставьте{' '}
            <span className="font-mono">OPENAI_API_KEY=sk-...</span>, очистите{' '}
            <span className="font-mono">OPENAI_BASE_URL</span>, перезапустите backend и нажмите
            «Синхронизация».
          </Notice>
        )}

        <div className="mb-6 grid gap-3 sm:grid-cols-3">
          {provs.map((p) => (
            <div key={p.id} className="oai-card p-4">
              <div className="flex items-center justify-between">
                <span className="text-[14px] font-medium capitalize">{p.id}</span>
                <span className={`oai-badge ${p.configured ? 'oai-badge-ok' : 'oai-badge-warn'}`}>
                  {p.configured ? 'ключ ок' : 'нет ключа'}
                </span>
              </div>
              <p className="mt-1 text-[12px] text-fg-secondary">
                {p.models} моделей
                {p.endpoint ? ` · ${p.endpoint}` : ''}
              </p>
            </div>
          ))}
        </div>

        <div className="overflow-hidden rounded-xl border border-border">
          {models.length === 0 ? (
            <EmptyState
              icon={<IconModel size={16} />}
              title="Моделей нет"
              description="Добавьте ключ провайдера в .env, затем синхронизируйте каталог."
              actions={
                <button type="button" onClick={sync} className="oai-btn-secondary">
                  Синхронизация
                </button>
              }
            />
          ) : (
            <table className="w-full">
              <thead>
                <tr className="border-b border-border bg-bg-accent text-[11px] uppercase tracking-wide text-fg-tertiary">
                  <th className="px-4 py-2 text-left font-medium">Модель</th>
                  <th className="px-4 py-2 text-left font-medium">Провайдер</th>
                  <th className="px-4 py-2 text-left font-medium">Контекст</th>
                  <th className="px-4 py-2 text-left font-medium">$ / Mtok</th>
                  <th className="px-4 py-2 text-left font-medium">Статус</th>
                  <th className="px-4 py-2 text-right font-medium">Действия</th>
                </tr>
              </thead>
              <tbody className="text-[13px]">
                {models.map((m) => (
                  <tr key={m.id} className="border-b border-border last:border-0 hover:bg-bg-hover">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2">
                        <span className={m.enabled ? '' : 'text-fg-tertiary line-through'}>
                          {m.model_id}
                        </span>
                        {m.is_default && <span className="oai-badge oai-badge-ok">default</span>}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-fg-secondary">
                      {m.provider}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-fg-secondary">
                      {m.context_window ? m.context_window.toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-fg-secondary">
                      {m.input_cost_per_mtok || m.output_cost_per_mtok
                        ? `${m.input_cost_per_mtok} / ${m.output_cost_per_mtok}`
                        : '—'}
                    </td>
                    <td className="px-4 py-2.5">
                      {m.last_status === 'unknown' ? (
                        <span className="text-[12px] text-fg-tertiary">не проверен</span>
                      ) : (
                        <span className="flex items-center gap-1.5 font-mono text-[12px] text-fg-secondary">
                          <StatusDot status={m.last_status === 'ok' ? 'completed' : 'failed'} />
                          {fmtMs(m.last_latency_ms)}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => check(m.id)}
                          disabled={checking === m.id}
                          className="oai-btn-secondary h-7 px-2 text-[12px]"
                        >
                          {checking === m.id ? <Spinner size={11} /> : 'Тест'}
                        </button>
                        <button
                          type="button"
                          onClick={() => toggle(m)}
                          className="oai-btn-secondary h-7 px-2 text-[12px]"
                        >
                          {m.enabled ? 'Выкл' : 'Вкл'}
                        </button>
                        <button
                          type="button"
                          onClick={() => platform.makeDefault(m.id).then(load)}
                          disabled={m.is_default}
                          className="oai-btn-secondary h-7 px-2 text-[12px]"
                        >
                          Default
                        </button>
                      </div>
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
