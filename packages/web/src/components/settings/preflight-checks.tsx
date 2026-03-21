import { useState, useEffect } from 'react';
import { CheckCircle, XCircle, AlertTriangle, RefreshCw } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { PreflightCheck, PreflightResponse } from '@/lib/api/types';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

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
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const result = await apiClient.getPreflight();
      setData(result);
    } catch {
      setData(null);
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

      {loading && !data ? (
        <div className="space-y-2">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-8 animate-pulse bg-[var(--muted)]" />
          ))}
        </div>
      ) : data ? (
        <div className="space-y-2">
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
