'use client';

import { useEffect, useState } from 'react';

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
};

export function PwaRegister() {
  useEffect(() => {
    if (typeof window === 'undefined' || !('serviceWorker' in navigator)) return;
    const onLoad = () => {
      navigator.serviceWorker.register('/sw.js').catch(() => {
        /* ignore offline/dev failures */
      });
    };
    if (document.readyState === 'complete') onLoad();
    else window.addEventListener('load', onLoad);
    return () => window.removeEventListener('load', onLoad);
  }, []);
  return null;
}

export function InstallAppBanner() {
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(null);
  const [hidden, setHidden] = useState(true);
  const [isStandalone, setIsStandalone] = useState(false);
  const [iosHint, setIosHint] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    const standalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true;
    setIsStandalone(standalone);
    const dismissed = localStorage.getItem('arix-pwa-dismiss') === '1';
    const ua = navigator.userAgent || '';
    const ios = /iphone|ipad|ipod/i.test(ua) && !(window as unknown as { MSStream?: unknown }).MSStream;
    setIosHint(ios && !standalone && !dismissed);
    setHidden(standalone || dismissed);

    const onBip = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
      if (!dismissed && !standalone) setHidden(false);
    };
    window.addEventListener('beforeinstallprompt', onBip);
    return () => window.removeEventListener('beforeinstallprompt', onBip);
  }, []);

  if (isStandalone || hidden) return null;

  const dismiss = () => {
    localStorage.setItem('arix-pwa-dismiss', '1');
    setHidden(true);
  };

  const install = async () => {
    if (!deferred) return;
    await deferred.prompt();
    await deferred.userChoice;
    setDeferred(null);
    setHidden(true);
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-[80] flex justify-center px-3 md:bottom-4">
      <div className="pointer-events-auto flex max-w-md items-start gap-3 rounded-xl border border-border-soft bg-bg-elevated/95 px-3 py-2.5 shadow-lg backdrop-blur">
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-fg-primary">Установить Arix</div>
          <p className="mt-0.5 text-[11.5px] leading-snug text-fg-muted">
            {iosHint
              ? 'На iPhone: Поделиться → На экран «Домой»'
              : deferred
                ? 'Как приложение на телефон или компьютер (PWA)'
                : 'Откройте в Chrome/Edge → меню → Установить приложение'}
          </p>
        </div>
        {deferred && (
          <button type="button" className="oai-btn-primary oai-btn-sm shrink-0" onClick={install}>
            Установить
          </button>
        )}
        <button
          type="button"
          className="oai-icon-btn shrink-0 text-fg-muted"
          title="Скрыть"
          onClick={dismiss}
        >
          ×
        </button>
      </div>
    </div>
  );
}
