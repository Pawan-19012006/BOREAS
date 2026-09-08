import { useEffect, useState } from 'react';

export type BackendState = 'checking' | 'online' | 'offline';

export function useBackendStatus(pollMs = 15000) {
  const [state, setState] = useState<BackendState>('checking');

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        // Real boreas-core backend, proxied at /boreas-api (see
        // vite.config.ts) -- this previously pointed at /api/health, which
        // proxies to an unrelated, not-running legacy service on port 3001
        // and made the toolbar permanently show "Backend Offline" even
        // while the real backend was healthy.
        const res = await fetch('/boreas-api/health');
        if (!res.ok) throw new Error(`status ${res.status}`);
        if (cancelled) return;
        setState('online');
      } catch {
        if (!cancelled) setState('offline');
      }
    };

    poll();
    const timer = setInterval(poll, pollMs);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [pollMs]);

  return { state };
}
