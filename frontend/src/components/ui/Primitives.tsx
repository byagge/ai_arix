'use client';

import { ReactNode } from 'react';
import { IconChevronRight } from '@/components/icons';

export function Page({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto w-full max-w-console px-4 pb-8 pt-4 animate-fade-in md:px-[34px] md:pb-20 md:pt-[26px]">
      {children}
    </div>
  );
}

export function WidePage({ children }: { children: ReactNode }) {
  return (
    <div className="w-full px-4 pb-8 pt-4 animate-fade-in md:px-[34px] md:pb-20 md:pt-6">
      {children}
    </div>
  );
}

export function PageTitle({
  children,
  actions,
  lede,
}: {
  children: ReactNode;
  actions?: ReactNode;
  lede?: ReactNode;
}) {
  return (
    <div className="mb-1.5">
      <div className="mb-1.5 flex min-h-[38px] items-center justify-between gap-4">
        <h1 className="text-[22px] font-semibold tracking-[-0.03em] md:text-[30px]">{children}</h1>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      {lede && <p className="oai-lede">{lede}</p>}
    </div>
  );
}

export function TopBar({
  title,
  children,
}: {
  title: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="sticky top-0 z-30 flex h-12 items-center justify-between gap-3 border-b border-border-soft bg-bg px-4">
      <div className="flex min-w-0 items-center gap-2 text-[15px] font-medium">{title}</div>
      <div className="flex shrink-0 items-center gap-2">{children}</div>
    </div>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex gap-0.5 rounded-full border border-border-soft bg-bg-accent p-0.5">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          onClick={() => onChange(o.id)}
          className={[
            'rounded-full px-2.5 py-1 text-[12px] font-medium transition-colors',
            value === o.id
              ? 'bg-bg-active text-white'
              : 'text-fg-tertiary hover:text-fg',
          ].join(' ')}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Tabs<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { id: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-5 border-b border-border">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          data-active={value === o.id}
          onClick={() => onChange(o.id)}
          className="oai-tab"
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function MetricCell({
  label,
  value,
  children,
  href,
}: {
  label: string;
  value: ReactNode;
  children?: ReactNode;
  href?: boolean;
}) {
  return (
    <div className="oai-metric">
      <div className="flex items-center gap-0.5 text-[12.5px] text-fg-tertiary">
        {label}
        {href !== false && <IconChevronRight size={12} className="opacity-65" />}
      </div>
      <div className="mt-1.5 text-[21px] font-medium tracking-[-0.02em]">{value}</div>
      {children && <div className="mt-auto pt-3.5">{children}</div>}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  actions,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-20 text-center">
      {icon && (
        <div className="mb-2 grid h-9 w-9 place-items-center rounded-md border border-border bg-bg-accent text-fg-tertiary">
          {icon}
        </div>
      )}
      <p className="text-[14px] font-medium">{title}</p>
      {description && (
        <p className="max-w-sm text-[13px] text-fg-tertiary">{description}</p>
      )}
      {actions && <div className="mt-4 flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Toggle({
  checked,
  onChange,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={[
        'relative h-5 w-[34px] shrink-0 rounded-full border transition-colors',
        checked
          ? 'border-accent bg-accent'
          : 'border-border bg-bg-surface3',
      ].join(' ')}
    >
      <span
        className={[
          'absolute top-[2px] h-3.5 w-3.5 rounded-full transition-all',
          checked ? 'left-4 bg-white' : 'left-[2px] bg-fg-tertiary',
        ].join(' ')}
      />
    </button>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="mb-5 max-w-[320px]">
      <label className="mb-1.5 block text-[12.5px] font-medium text-fg-secondary">
        {label}
      </label>
      {children}
      {hint && <p className="mt-1.5 text-[12px] text-fg-muted">{hint}</p>}
    </div>
  );
}

export function Row({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-[13px] text-fg-secondary">{label}</span>
      <div className="w-[132px] shrink-0">{children}</div>
    </div>
  );
}

export function Section({
  title,
  children,
  action,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <section className="mb-8">
      <div className="mb-2.5 flex items-center justify-between">
        <h2 className="text-[15px] font-semibold">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

export function Spinner({ size = 12 }: { size?: number }) {
  return (
    <span
      style={{ width: size, height: size }}
      className="inline-block animate-spin rounded-full border border-current border-t-transparent"
    />
  );
}

export function StatusDot({ status }: { status: string }) {
  const failed = status === 'failed' || status === 'error';
  const ok = status === 'completed' || status === 'ok' || status === 'succeeded';
  return (
    <span
      title={status}
      className={[
        'inline-block h-1.5 w-1.5 shrink-0 rounded-full',
        failed ? 'bg-danger' : ok ? 'bg-accent' : 'bg-fg-tertiary',
      ].join(' ')}
    />
  );
}

export function Notice({ children, tone = 'default' }: { children: ReactNode; tone?: 'default' | 'warn' | 'bad' }) {
  const toneClass =
    tone === 'warn'
      ? 'border-amber-line bg-amber-bg/40 text-amber-text'
      : tone === 'bad'
        ? 'border-danger/35 bg-danger/10 text-[#ffa2a5]'
        : 'border-border bg-bg-elevated text-fg-secondary';
  return (
    <div className={`mb-4 flex items-start gap-2.5 rounded-md border px-3.5 py-3 text-[13px] ${toneClass}`}>
      {children}
    </div>
  );
}

export function Pill({
  children,
  tone = 'default',
}: {
  children: ReactNode;
  tone?: 'default' | 'ok' | 'warn' | 'bad' | 'processing';
}) {
  const cls =
    tone === 'ok'
      ? 'oai-badge-ok'
      : tone === 'warn'
        ? 'oai-badge-warn'
        : tone === 'bad'
          ? 'oai-badge-bad'
          : tone === 'processing'
            ? 'border-blue/30 bg-blue/10 text-blue'
            : '';
  return <span className={`oai-badge ${cls}`}>{children}</span>;
}
