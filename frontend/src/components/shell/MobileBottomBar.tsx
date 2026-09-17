'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import {
  IconCard,
  IconChat,
  IconHome,
  IconMore,
  IconThreads,
} from '@/components/icons';

/** Compact app tabs — mobile only. Desktop keeps full sidebar. */
const TABS = [
  { href: '/', label: 'Главная', Icon: IconHome, match: (p: string) => p === '/' },
  {
    href: '/clients',
    label: 'Чаты',
    Icon: IconThreads,
    match: (p: string) => p.startsWith('/clients'),
  },
  {
    href: '/payments-admin',
    label: 'Платежи',
    Icon: IconCard,
    match: (p: string) => p.startsWith('/payments'),
  },
  {
    href: '/chat',
    label: 'Тест',
    Icon: IconChat,
    match: (p: string) => p.startsWith('/chat'),
  },
  {
    href: '/settings',
    label: 'Ещё',
    Icon: IconMore,
    match: (p: string) =>
      p.startsWith('/settings') ||
      p.startsWith('/storage') ||
      p.startsWith('/models') ||
      p.startsWith('/logs') ||
      p.startsWith('/api-keys'),
  },
];

export function MobileBottomBar() {
  return (
    <Suspense fallback={null}>
      <MobileBottomBarInner />
    </Suspense>
  );
}

function MobileBottomBarInner() {
  const pathname = usePathname();
  const search = useSearchParams();
  // Hide tab bar inside an open chat — like a native messenger
  const chatOpen = pathname.startsWith('/clients') && !!search.get('id');
  if (chatOpen) return null;

  return (
    <nav className="mobile-bottom-bar md:hidden" aria-label="Основная навигация">
      {TABS.map(({ href, label, Icon, match }) => {
        const active = match(pathname);
        return (
          <Link
            key={href}
            href={href}
            className={['mobile-tab', active ? 'mobile-tab-active' : ''].join(' ')}
          >
            <Icon size={22} />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
