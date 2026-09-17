'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import {
  IconBook,
  IconCard,
  IconChat,
  IconChevronRight,
  IconChevronUpDown,
  IconExternal,
  IconHome,
  IconKey,
  IconLogs,
  IconModel,
  IconMonitor,
  IconMoon,
  IconPanel,
  IconSearch,
  IconSettings,
  IconStorage,
  IconSun,
  IconThreads,
  IconUser,
} from '@/components/icons';
import { MobileBottomBar } from '@/components/shell/MobileBottomBar';

/** Только управление ИИ-сотрудником — без лишних разделов платформы. */
const NAV = [
  { href: '/', label: 'Главная', Icon: IconHome },
  { href: '/clients', label: 'Клиенты', Icon: IconThreads },
  { href: '/payments-admin', label: 'Платежи', Icon: IconCard },
  { href: '/chat', label: 'Тест чата', Icon: IconChat },
  { href: '/storage', label: 'Знания', Icon: IconStorage },
  { href: '/models', label: 'Модели', Icon: IconModel },
  { href: '/logs', label: 'Логи', Icon: IconLogs },
  { href: '/settings', label: 'Настройки', Icon: IconSettings },
];

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [brandOpen, setBrandOpen] = useState(false);

  const isActive = (href: string) =>
    href === '/' ? pathname === '/' : pathname.startsWith(href);

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-bg md:h-screen">
      {/* Desktop rail — unchanged layout; completely hidden on mobile */}
      <aside
        className="relative z-40 hidden shrink-0 flex-col border-r border-border-soft bg-bg-rail transition-[width] duration-[240ms] ease-[cubic-bezier(0.4,0,0.2,1)] md:flex"
        style={{ width: collapsed ? 56 : 232 }}
      >
        <div className="flex items-center gap-1 px-2 pb-2.5 pt-2.5">
          {!collapsed ? (
            <button
              type="button"
              onClick={() => setBrandOpen((o) => !o)}
              className="flex h-7 min-w-0 flex-1 items-center gap-1.5 rounded-sm px-2 text-[13px] font-semibold transition-colors hover:bg-bg-hover"
            >
              <span className="oai-brand-mark">
                <IconUser size={13} />
              </span>
              <span className="truncate">Arix</span>
              <IconChevronUpDown size={13} className="shrink-0 text-fg-muted" />
            </button>
          ) : (
            <div className="mx-auto">
              <span className="oai-brand-mark">
                <IconUser size={13} />
              </span>
            </div>
          )}
          <button
            type="button"
            onClick={() => setCollapsed((c) => !c)}
            className="oai-icon-btn"
            title={collapsed ? 'Развернуть' : 'Свернуть'}
          >
            <IconPanel size={16} />
          </button>
        </div>

        {brandOpen && !collapsed && <BrandMenu onClose={() => setBrandOpen(false)} />}

        <div className="px-2 pb-3">
          <button type="button" className="oai-search-box" title="Поиск">
            <IconSearch size={14} className="shrink-0 opacity-70" />
            {!collapsed && (
              <>
                <span className="flex-1 text-left">Поиск</span>
                <span className="oai-kbd">Ctrl+K</span>
              </>
            )}
          </button>
        </div>

        <nav className="oai-scroll flex-1 space-y-px overflow-y-auto overflow-x-hidden px-2">
          {NAV.map(({ href, label, Icon }) => (
            <Link
              key={href}
              href={href}
              data-active={isActive(href)}
              className="oai-nav-item"
              title={collapsed ? label : undefined}
              style={collapsed ? { justifyContent: 'center', padding: 0, gap: 0 } : undefined}
            >
              <Icon size={16} className="shrink-0 opacity-90" />
              {!collapsed && <span className="truncate">{label}</span>}
            </Link>
          ))}
        </nav>

        <div className="px-2 pb-2 pt-2">
          <AccountMenu collapsed={collapsed} />
        </div>
      </aside>

      <main className="oai-scroll mobile-main flex-1 overflow-y-auto animate-fade-in">
        {children}
      </main>

      <MobileBottomBar />
    </div>
  );
}

function BrandMenu({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return (
    <div
      ref={ref}
      className="animate-pop absolute left-2 top-11 z-[60] w-[216px] rounded-md border border-border bg-bg-accent p-1 shadow-menu"
    >
      <Link
        href="/settings"
        onClick={onClose}
        className="flex items-center gap-2 rounded-sm px-2.5 py-2 text-[13px] text-fg-secondary hover:bg-bg-hover hover:text-fg"
      >
        <IconSettings size={14} /> Настройки
      </Link>
      <a
        href={`${API_BASE}/docs`}
        target="_blank"
        rel="noreferrer"
        onClick={onClose}
        className="flex items-center gap-2 rounded-sm px-2.5 py-2 text-[13px] text-fg-secondary hover:bg-bg-hover hover:text-fg"
      >
        <IconBook size={14} /> API docs
        <IconExternal size={11} className="ml-auto text-fg-muted" />
      </a>
    </div>
  );
}

function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  return (
    <div ref={ref} className="relative border-t border-border-soft pt-2.5">
      {open && (
        <div className="animate-pop absolute bottom-[calc(100%+6px)] left-0 z-50 w-[248px] rounded-lg border border-border bg-bg-accent py-1.5 shadow-menu">
          <div className="px-3 py-1.5">
            <p className="text-[12px] text-fg-tertiary">ИИ-сотрудник</p>
            <div className="mt-2">
              <ThemeSwitch />
            </div>
          </div>
          <div className="my-1 border-t border-border" />
          <Link
            href="/settings"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 px-3 py-1.5 text-[13px] text-fg-secondary transition-colors hover:bg-bg-hover hover:text-fg"
          >
            <IconSettings size={15} />
            Настройки агента
          </Link>
          <Link
            href="/api-keys"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 px-3 py-1.5 text-[13px] text-fg-secondary transition-colors hover:bg-bg-hover hover:text-fg"
          >
            <IconKey size={15} />
            Ключи API
          </Link>
          <a
            href={`${API_BASE}/docs`}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-2.5 px-3 py-1.5 text-[13px] text-fg-secondary transition-colors hover:bg-bg-hover hover:text-fg"
          >
            <IconBook size={15} />
            Документация
            <IconExternal size={11} className="ml-auto text-fg-muted" />
          </a>
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 transition-colors hover:bg-bg-hover"
        style={collapsed ? { justifyContent: 'center' } : undefined}
      >
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-bg-surface3 text-fg-secondary">
          <IconUser size={14} />
        </span>
        {!collapsed && (
          <span className="min-w-0 flex-1 text-left leading-tight">
            <span className="block truncate text-[12.5px] font-medium">Администратор</span>
            <span className="block truncate text-[11px] text-fg-muted">Arix</span>
          </span>
        )}
        {!collapsed && <IconChevronRight size={13} className="text-fg-muted" />}
      </button>
    </div>
  );
}

function ThemeSwitch() {
  const [mode, setMode] = useState<'system' | 'light' | 'dark'>('dark');

  useEffect(() => {
    const stored = localStorage.getItem('arix-theme');
    setMode(stored === 'light' || stored === 'dark' ? stored : 'dark');
  }, []);

  const apply = (next: 'system' | 'light' | 'dark') => {
    setMode(next);
    if (next === 'system') {
      localStorage.removeItem('arix-theme');
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.classList.toggle('dark', prefersDark);
    } else {
      localStorage.setItem('arix-theme', next);
      document.documentElement.classList.toggle('dark', next === 'dark');
    }
  };

  const options = [
    { id: 'system' as const, Icon: IconMonitor, title: 'Система' },
    { id: 'light' as const, Icon: IconSun, title: 'Светлая' },
    { id: 'dark' as const, Icon: IconMoon, title: 'Тёмная' },
  ];

  return (
    <div className="inline-flex rounded-md border border-border p-0.5">
      {options.map(({ id, Icon, title }) => (
        <button
          key={id}
          type="button"
          onClick={() => apply(id)}
          title={title}
          className={[
            'grid h-6 w-8 place-items-center rounded-sm transition-colors',
            mode === id ? 'bg-bg-active text-fg' : 'text-fg-muted hover:text-fg',
          ].join(' ')}
        >
          <Icon size={13} />
        </button>
      ))}
    </div>
  );
}
