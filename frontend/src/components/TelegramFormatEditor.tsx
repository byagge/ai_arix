'use client';

import { useRef } from 'react';

type Props = {
  value: string;
  onChange: (v: string) => void;
  rows?: number;
};

/** Telegram HTML formatter — bold/italic/quote/code (tap-to-copy) + premium emoji as-is. */
export function TelegramFormatEditor({ value, onChange, rows = 8 }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  const wrap = (before: string, after: string) => {
    const el = ref.current;
    if (!el) {
      onChange(`${before}${value}${after}`);
      return;
    }
    const start = el.selectionStart;
    const end = el.selectionEnd;
    const selected = value.slice(start, end) || 'текст';
    const next = value.slice(0, start) + before + selected + after + value.slice(end);
    onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + before.length + selected.length + after.length;
      el.setSelectionRange(pos, pos);
    });
  };

  const insert = (snippet: string) => {
    const el = ref.current;
    if (!el) {
      onChange(value + snippet);
      return;
    }
    const start = el.selectionStart;
    const next = value.slice(0, start) + snippet + value.slice(el.selectionEnd);
    onChange(next);
    requestAnimationFrame(() => {
      el.focus();
      const pos = start + snippet.length;
      el.setSelectionRange(pos, pos);
    });
  };

  const tools: { label: string; title: string; run: () => void }[] = [
    { label: 'B', title: 'Жирный', run: () => wrap('<b>', '</b>') },
    { label: 'I', title: 'Курсив', run: () => wrap('<i>', '</i>') },
    { label: 'U', title: 'Подчёркнутый', run: () => wrap('<u>', '</u>') },
    { label: 'S', title: 'Зачёркнутый', run: () => wrap('<s>', '</s>') },
    { label: '</>', title: 'Код · клик-копия', run: () => wrap('<code>', '</code>') },
    { label: '«»', title: 'Цитата', run: () => wrap('<blockquote>', '</blockquote>') },
    { label: '•••', title: 'Спойлер', run: () => wrap('<tg-spoiler>', '</tg-spoiler>') },
    { label: '{amt}', title: 'Сумма', run: () => insert('{amount}') },
    { label: '{adr}', title: 'Адрес', run: () => insert('{address}') },
  ];

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-1">
        {tools.map((t) => (
          <button
            key={t.label}
            type="button"
            title={t.title}
            onClick={t.run}
            className="oai-btn-secondary !h-7 !px-2 font-mono text-[11px]"
          >
            {t.label}
          </button>
        ))}
      </div>
      <textarea
        ref={ref}
        className="oai-textarea text-[13px]"
        rows={rows}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        spellCheck={false}
        placeholder="Текст сообщения… Premium emoji вставляйте как есть"
      />
      <p className="mt-1.5 text-[11px] leading-snug text-fg-muted">
        Telegram HTML: <code className="text-fg-tertiary">&lt;b&gt;</code> жирный,{' '}
        <code className="text-fg-tertiary">&lt;i&gt;</code> курсив,{' '}
        <code className="text-fg-tertiary">&lt;code&gt;</code> клик-копия,{' '}
        <code className="text-fg-tertiary">&lt;blockquote&gt;</code> цитата. Premium emoji —
        вставьте из Telegram, не трогаем.
      </p>
      {value.trim() && (
        <div className="mt-3 rounded-md border border-border bg-bg px-3 py-2.5">
          <div className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-fg-muted">
            Превью
          </div>
          <div
            className="tg-preview text-[13.5px] leading-relaxed text-fg"
            dangerouslySetInnerHTML={{
              __html: sanitizeTgPreview(
                value.replace(/\{amount\}/g, '100').replace(/\{address\}/g, 'TXxx…demo')
              ),
            }}
          />
        </div>
      )}
    </div>
  );
}

function sanitizeTgPreview(html: string): string {
  // allow only Telegram subset tags
  const allowed = /<\/?(?:b|i|u|s|code|pre|blockquote|tg-spoiler|a)(?:\s[^>]*)?>/gi;
  let out = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  // restore allowed tags (re-match on escaped is messy — simpler whitelist pass)
  out = html
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/&lt;(\/?(?:b|i|u|s|code|pre|blockquote|tg-spoiler))&gt;/gi, '<$1>')
    .replace(/&lt;a\s+href=(?:&quot;|')([^"']+)(?:&quot;|')&gt;/gi, '<a href="$1">')
    .replace(/&lt;\/a&gt;/gi, '</a>')
    .replace(/\n/g, '<br/>');
  void allowed;
  return out;
}
