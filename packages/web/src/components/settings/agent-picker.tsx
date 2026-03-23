import { useState, useEffect, useCallback } from 'react';
import { Bot, Check } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { AgentBackend } from '@/lib/api/types';
import { Card } from '@/components/ui/card';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export function AgentPicker() {
  const [backends, setBackends] = useState<AgentBackend[]>([]);
  const [defaultBackend, setDefaultBackend] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiClient.getChatAgents();
        const sorted = [...data.backends].sort((a, b) => {
          if (a.available === b.available) return 0;
          return a.available ? -1 : 1;
        });
        setBackends(sorted);
        setDefaultBackend(data.default);
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
      <p className="mb-3 text-xs text-[var(--muted-foreground)]">Click to set the default agent for new tasks.</p>
      {loading ? (
        <div className="h-8 animate-pulse bg-[var(--muted)]" />
      ) : backends.length === 0 ? (
        <p className="text-sm text-[var(--muted-foreground)]">No backends available</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {backends.map((backend) => (
            <Button
              key={backend.name}
              variant="outline"
              size="xs"
              onClick={() => selectBackend(backend.name)}
              disabled={saving}
              title={!backend.available ? 'Not installed' : undefined}
              className={cn(
                'transition-colors',
                backend.name === defaultBackend
                  ? 'border-[var(--primary)] bg-[var(--primary)]/10 text-[var(--primary)]'
                  : 'border-[color:var(--border-subtle)] text-[var(--muted-foreground)] hover:bg-[color:var(--surface-2)]',
                !backend.available && 'opacity-40',
              )}
            >
              {backend.name === defaultBackend ? (
                <Check className="size-3" />
              ) : (
                <Bot className="size-3" />
              )}
              {backend.name}
            </Button>
          ))}
        </div>
      )}
    </Card>
  );
}
