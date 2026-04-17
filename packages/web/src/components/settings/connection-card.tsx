import { useEffect, useState } from 'react';
import { useAtomValue } from 'jotai';
import { Wifi, WifiOff, ExternalLink } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import { Card } from '@/components/ui/card';
import { KAGAN_URLS } from '@/lib/constants';

export function ConnectionCard() {
  const sseConnected = useAtomValue(sseConnectedAtom);
  const baseUrl = apiClient.getBaseUrl() || window.location.origin;
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    apiClient.getHealth().then((h) => setVersion(h.version)).catch(() => {});
  }, []);

  return (
    <Card className="p-4">
      <h2 className="mb-3 text-sm font-medium">Connection</h2>
      <div className="space-y-3">
        <div className="flex items-center justify-between text-sm">
          <span className="text-[var(--muted-foreground)]">Server</span>
          <span className="font-mono text-xs">{baseUrl}</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-[var(--muted-foreground)]">Mode</span>
          <span>Bundled</span>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-[var(--muted-foreground)]">Events</span>
          <div className="flex items-center gap-2">
            {sseConnected ? (
              <>
                <Wifi className="size-3 text-[var(--kagan-success)]" />
                <span className="text-[var(--kagan-success)]">Connected</span>
              </>
            ) : (
              <>
                <WifiOff className="size-3 text-[var(--destructive)]" />
                <span className="text-[var(--destructive)]">Reconnecting...</span>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-[var(--muted-foreground)]">Version</span>
          <a
            href={KAGAN_URLS.github}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 font-mono text-xs hover:text-[var(--foreground)]"
            title="View on GitHub"
          >
            {version ?? '…'}
            <span className="text-[var(--muted-foreground)]">·</span>
            <span>MIT</span>
            <ExternalLink className="size-3 text-[var(--muted-foreground)]" />
          </a>
        </div>
      </div>
    </Card>
  );
}
