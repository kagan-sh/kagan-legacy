import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { AgentBackend, PreflightCheck, PreflightResponse } from '@/lib/api/types';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

function sortBackends(backends: AgentBackend[]): AgentBackend[] {
  return [...backends].sort((a, b) => {
    if (a.reference !== b.reference) return a.reference ? -1 : 1;
    if (a.available !== b.available) return a.available ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

function getStatusIcon(status: string): typeof CheckCircle {
  switch (status) {
    case 'fail':
      return XCircle;
    case 'warn':
      return AlertTriangle;
    default:
      return CheckCircle;
  }
}

function getStatusColor(status: string): string {
  switch (status) {
    case 'fail':
      return 'text-[var(--destructive)]';
    case 'warn':
      return 'text-[var(--kagan-warning)]';
    default:
      return 'text-[var(--kagan-success)]';
  }
}

export function PreflightChecks() {
  const [data, setData] = useState<PreflightResponse | null>(null);
  const [backends, setBackends] = useState<AgentBackend[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const [result, agents] = await Promise.all([
        apiClient.getPreflight(),
        apiClient.getChatAgents(),
      ]);
      setData(result);
      setBackends(sortBackends(agents.backends));
    } catch {
      setData(null);
      setBackends([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  return (
    <Card className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium">System Checks</h3>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={load}
          disabled={loading}
          className="text-[var(--muted-foreground)]"
          aria-label="Refresh checks"
        >
          <RefreshCw className={`size-4 ${loading ? 'animate-spin' : ''}`} />
        </Button>
      </div>
      {!loading && backends.some((backend) => backend.reference) && (
        <div className="mb-3 space-y-2 rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-2)]/50 p-3">
          <p className="text-xs font-medium text-foreground">Reference backends</p>
          <div className="flex flex-wrap gap-2">
            {backends
              .filter((backend) => backend.reference)
              .map((backend) => (
                <Badge key={backend.name} variant={backend.available ? 'outline' : 'secondary'} className="gap-1.5">
                  {backend.name}
                  {!backend.available && <span className="text-[10px] uppercase tracking-wide">Unavailable</span>}
                </Badge>
              ))}
          </div>
        </div>
      )}

      {loading && !data ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-8 animate-pulse bg-[var(--muted)]" />
          ))}
        </div>
      ) : data ? (
        <div className="space-y-3">
          {data.checks.some((check) => check.status !== 'pass' && /backend/i.test(check.name)) && backends.some((backend) => backend.reference && backend.available) && (
            <div className="rounded-md border border-[color:var(--border-subtle)] bg-[color:var(--surface-2)]/70 p-3 text-xs text-[var(--muted-foreground)]">
              Try a reference backend first if this check is warning or failing.
            </div>
          )}
          {data.checks.map((check: PreflightCheck) => {
            const Icon = getStatusIcon(check.status);
            const color = getStatusColor(check.status);
            return (
              <div key={check.name} className="flex items-start gap-2 text-sm">
                <Icon className={`mt-0.5 size-4 shrink-0 ${color}`} />
                <div className="flex-1">
                  <p className="font-medium">{check.name}</p>
                  <p className="text-xs text-[var(--muted-foreground)]">{check.message}</p>
                  {check.fix_hint && (
                    <p className="mt-1 text-xs text-[var(--kagan-warning)]">{check.fix_hint}</p>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-sm text-[var(--muted-foreground)]">Failed to load checks</p>
      )}
    </Card>
  );
}
