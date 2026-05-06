import { useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api/client';

export interface PermissionRequest {
  futureId: string;
  toolName: string;
  sessionId: string;
}

interface Props {
  request: PermissionRequest | null;
  onResolved: () => void;
}

export function PermissionDialog({ request, onResolved }: Props) {
  const [loading, setLoading] = useState(false);

  async function resolve(outcome: string) {
    if (!request) return;
    // Map "Allow all for session" to allow_always — the ACP layer only accepts
    // allow_once / allow_always / deny / deny_feedback. True session-wide
    // grants for all tools require server-side approval state (not yet wired);
    // until then, allow_always at least keeps the agent unblocked for this
    // tool instead of being silently cancelled.
    const wireOutcome = outcome === 'allow_all_session' ? 'allow_always' : outcome;
    setLoading(true);
    try {
      await apiClient.resolvePermission(request.sessionId, request.futureId, wireOutcome);
      onResolved();
    } finally {
      setLoading(false);
    }
  }

  return (
    <Dialog open={!!request}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Permission required</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          Kagan wants to run <span className="font-medium">{request?.toolName}</span>
        </p>
        <div className="flex flex-col gap-2 mt-4">
          <Button onClick={() => void resolve('allow_once')} disabled={loading}>
            Allow once
          </Button>
          <Button variant="outline" onClick={() => void resolve('allow_always')} disabled={loading}>
            Allow tool for session
          </Button>
          <Button variant="outline" onClick={() => void resolve('allow_all_session')} disabled={loading}>
            Allow all for session
          </Button>
          <Button variant="destructive" onClick={() => void resolve('deny')} disabled={loading}>
            Reject
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
