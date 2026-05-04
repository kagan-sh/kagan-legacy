import { useState, useEffect, useCallback } from 'react';
import { Bot, Check } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { AgentBackend } from '@kagan/shared-api-client';
import { Card } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

function sortBackends(backends: AgentBackend[]): AgentBackend[] {
  return [...backends].sort((a, b) => {
    if (a.reference !== b.reference) return a.reference ? -1 : 1;
    if (a.available !== b.available) return a.available ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

export function AgentPicker() {
  const [backends, setBackends] = useState<AgentBackend[]>([]);
  const [defaultBackend, setDefaultBackend] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [recommendedBackend, setRecommendedBackend] = useState<{ backend: string; success_rate: number } | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const [settings, agents] = await Promise.all([
          apiClient.getSettings(),
          apiClient.getChatAgents(),
        ]);

        const useRecommended = String(settings.use_recommended_backend) === 'true';

        const availableBackends = sortBackends(agents.backends);
        setBackends(availableBackends);
        setDefaultBackend(agents.default);

        try {
          const rec = await apiClient.getRecommendedBackend();
          if (rec.backend) {
            const recBackend = { backend: rec.backend, success_rate: rec.success_rate || 0 };
            setRecommendedBackend(recBackend);

            // Auto-select recommended backend if enabled and available
            if (useRecommended && availableBackends.some(b => b.name === rec.backend && b.available)) {
              setDefaultBackend(rec.backend);
              try {
                await apiClient.setSettings({ default_agent_backend: rec.backend });
              } catch {
                // Silent fail on auto-select
              }
            }
          }
        } catch {
          // Recommendation failed, continue without it
        }
      } catch {
        toast.error('Failed to load agent backends');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const selectBackend = useCallback(
    async (backend: string) => {
      if (backend === defaultBackend || saving) return;
      setSaving(true);
      try {
        await apiClient.setSettings({
          default_agent_backend: backend,
        });
        setDefaultBackend(backend);
        toast.success(`Agent backend set to ${backend}`);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to set agent backend');
      } finally {
        setSaving(false);
      }
    },
    [defaultBackend, saving],
  );

  return (
    <Card className="p-4">
      <h3 className="mb-1 text-sm font-medium">Agent Backend</h3>
      <p className="mb-3 text-xs text-[var(--muted-foreground)]">
        Reference backends are surfaced first. Current default: <span className="font-medium text-foreground">{defaultBackend || 'unknown'}</span>
      </p>
      {loading ? (
        <div className="h-8 animate-pulse bg-[var(--muted)]" />
      ) : backends.length === 0 ? (
        <p className="text-sm text-[var(--muted-foreground)]">No backends available</p>
      ) : (
        <div className="space-y-2">
          {backends.some((backend) => backend.reference) && (
            <div className="flex flex-wrap gap-2">
              {backends
                .filter((backend) => backend.reference)
                .map((backend) => (
                  <Badge key={backend.name} variant="outline" className="gap-1.5">
                    <Bot className="size-3" />
                    {backend.name}
                    {backend.available ? null : <span className="text-[10px] uppercase tracking-wide text-[var(--muted-foreground)]">Unavailable</span>}
                  </Badge>
                ))}
            </div>
          )}
          <div className="flex flex-wrap gap-2">
          {backends.filter((backend) => backend.available).map((backend) => (
            <Button
              key={backend.name}
              variant="outline"
              size="xs"
              onClick={() => selectBackend(backend.name)}
              disabled={saving}
              className={cn(
                'min-w-0 gap-1.5 transition-colors',
                backend.name === defaultBackend
                  ? 'border-[var(--primary)] bg-[var(--primary)]/10 text-[var(--primary)]'
                  : 'border-[color:var(--border-subtle)] text-[var(--muted-foreground)] hover:bg-[color:var(--surface-2)]',
              )}
            >
              {backend.name === defaultBackend ? (
                <Check className="size-3" />
              ) : (
                <Bot className="size-3" />
              )}
              <span>{backend.name}</span>
              {recommendedBackend?.backend === backend.name && (
                <Badge className="px-1.5 py-0 text-[10px] bg-[var(--primary)]/20 text-[var(--primary)] border-[var(--primary)]/30">
                  Recommended
                </Badge>
              )}
              {recommendedBackend?.backend === backend.name && (
                <span className="text-[10px] text-[var(--muted-foreground)]">
                  {(recommendedBackend.success_rate * 100).toFixed(0)}% success
                </span>
              )}
              {backend.reference && <Badge variant="outline" className="px-1.5 py-0 text-[10px]">Reference</Badge>}
            </Button>
          ))}
          </div>
        </div>
      )}
    </Card>
  );
}
