'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { IconPlus, IconRefresh, IconStorage, IconTrash, IconX } from '@/components/icons';
import { EmptyState, Notice, Spinner, TopBar, WidePage } from '@/components/ui/Primitives';

const BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

interface Doc {
  id: number;
  filename: string;
  file_type: string;
  chunk_count: number;
  indexed: boolean;
  created_at: string;
}

export default function StoragePage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${BASE}/api/knowledge`, { cache: 'no-store' });
      setDocs(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Не удалось загрузить файлы');
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const uploadFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    setBusy(true);
    setError(null);
    try {
      for (const file of list) {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(`${BASE}/api/knowledge/upload`, { method: 'POST', body: form });
        if (!res.ok) throw new Error(`Ошибка загрузки ${file.name}: ${res.status}`);
      }
      await load();
      setModalOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ошибка загрузки');
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const act = async (id: number, path: string, method: string) => {
    setBusy(true);
    try {
      await fetch(`${BASE}/api/knowledge/${id}${path}`, { method });
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <TopBar title="Знания">
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="oai-btn-primary gap-1.5"
        >
          <IconPlus size={14} /> Загрузить
        </button>
      </TopBar>

      <WidePage>
        {error && <Notice tone="bad">{error}</Notice>}

        <div className="overflow-hidden rounded-xl border border-border">
          {docs.length === 0 ? (
            <EmptyState
              icon={<IconStorage size={16} />}
              title="Файлов пока нет"
              description="PDF, DOCX, TXT, фото — агент сможет опираться на них в ответах."
              actions={
                <button type="button" className="oai-btn-primary" onClick={() => setModalOpen(true)}>
                  Загрузить файл
                </button>
              }
            />
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border bg-bg-accent text-[11px] uppercase tracking-wide text-fg-tertiary">
                  <th className="px-4 py-2 text-left font-medium">Файл</th>
                  <th className="px-4 py-2 text-left font-medium">Тип</th>
                  <th className="px-4 py-2 text-right font-medium">Чанки</th>
                  <th className="px-4 py-2 text-left font-medium">Статус</th>
                  <th className="px-4 py-2 text-right font-medium">Действия</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.id} className="border-b border-border last:border-0 hover:bg-bg-hover">
                    <td className="px-4 py-2.5">{d.filename}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] uppercase text-fg-secondary">
                      {d.file_type}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-[12px]">
                      {d.chunk_count}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`oai-badge ${d.indexed ? 'oai-badge-ok' : ''}`}>
                        {d.indexed ? 'indexed' : 'pending'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5">
                      <div className="flex justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => act(d.id, '/reindex', 'POST')}
                          className="oai-btn-secondary h-7 gap-1 px-2 text-[12px]"
                        >
                          <IconRefresh size={12} /> Reindex
                        </button>
                        <button
                          type="button"
                          onClick={() => act(d.id, '', 'DELETE')}
                          className="oai-btn-secondary h-7 gap-1 px-2 text-[12px]"
                        >
                          <IconTrash size={12} /> Delete
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

      {modalOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          onClick={() => !busy && setModalOpen(false)}
        >
          <div
            className="w-full max-w-md animate-fade-in rounded-xl border border-border bg-bg-elevated p-5 shadow-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-[16px] font-semibold">Загрузка в знания</h2>
              <button
                type="button"
                className="oai-icon-btn"
                disabled={busy}
                onClick={() => setModalOpen(false)}
              >
                <IconX size={16} />
              </button>
            </div>

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                if (e.dataTransfer.files?.length) uploadFiles(e.dataTransfer.files);
              }}
              className={[
                'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-6 py-12 text-center transition-colors',
                dragOver
                  ? 'border-accent bg-accent/10 text-fg'
                  : 'border-border bg-bg text-fg-tertiary hover:border-border-strong hover:text-fg-secondary',
              ].join(' ')}
              onClick={() => fileRef.current?.click()}
            >
              <IconStorage size={22} />
              <p className="text-[14px] font-medium text-fg">
                Перетащите файл сюда
              </p>
              <p className="text-[12.5px]">
                или нажмите, чтобы выбрать · PDF, DOCX, TXT, фото и др.
              </p>
              {busy && (
                <span className="mt-2 inline-flex items-center gap-2 text-[12px] text-accent">
                  <Spinner size={12} /> Загрузка…
                </span>
              )}
            </div>

            <input
              ref={fileRef}
              type="file"
              multiple
              accept="*/*"
              className="hidden"
              onChange={(e) => {
                if (e.target.files?.length) uploadFiles(e.target.files);
              }}
            />

            <button
              type="button"
              className="oai-btn-secondary mt-4 w-full"
              disabled={busy}
              onClick={() => fileRef.current?.click()}
            >
              Выбрать файл
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
