import { useEffect, useState } from 'react';
import { useAtomValue } from 'jotai';
import { Wifi, WifiOff, RefreshCw } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import { kaganWs } from '@/lib/api/websocket';
import { wsConnectedAtom } from '@/lib/atoms/connection';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export function ConnectionCard() {
  const wsConnected = useAtomValue(wsConnectedAtom);
  const baseUrl = apiClient.getBaseUrl() || window.location.origin;
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    apiClient.getHealth().then((h) => setVersion(h.version)).catch(() => {});
  }, []);

  const handleReconnect = () => {
    kaganWs.disconnect();
    setTimeout(() => kaganWs.connect(), 100);
  };

  return (
    <Card className="p-4">
      <h3 className="mb-3 text-sm font-medium">Connection</h3>
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
          <span className="text-[var(--muted-foreground)]">WebSocket</span>
          <div className="flex items-center gap-2">
            {wsConnected ? (
              <>
                <Wifi className="size-3 text-[var(--kagan-success)]" />
                <span className="text-[var(--kagan-success)]">Connected</span>
              </>
            ) : (
              <>
                <WifiOff className="size-3 text-[var(--destructive)]" />
                <span className="text-[var(--destructive)]">Disconnected</span>
                <Button variant="outline" size="xs" onClick={handleReconnect} className="ml-2">
                  <RefreshCw className="size-3" />
                  Reconnect
                </Button>
              </>
            )}
          </div>
        </div>
        <div className="flex items-center justify-between text-sm">
          <span className="text-[var(--muted-foreground)]">Version</span>
          <span className="font-mono text-xs">{version ?? '…'}</span>
        </div>
      </div>
    </Card>
  );
}
