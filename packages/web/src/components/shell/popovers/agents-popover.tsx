import { useEffect, useState, useCallback } from 'react';
import { useAtomValue } from 'jotai';
import { tasksAtom } from '@/lib/atoms/board';
import { apiClient } from '@/lib/api/client';
import { PopoverPanel, PopoverTitle, useShellPopover } from '../popover';
import type { AgentBackendResponse } from '@kagan/shared-api-client';

interface AgentsPopoverProps {
  /** Whether to open aligned left or right of the trigger. */
  align?: 'left' | 'right';
}

export function AgentsPopover({ align = 'left' }: AgentsPopoverProps) {
  const { isOpen } = useShellPopover('agents', align);
  const tasks = useAtomValue(tasksAtom);
  const [backends, setBackends] = useState<AgentBackendResponse[]>([]);

  // Count tasks running per agent backend
  const runningCounts = useCallback((): Record<string, number> => {
    const counts: Record<string, number> = {};
    for (const task of tasks) {
      if (task.active_session?.agent_backend) {
        const name = task.active_session.agent_backend;
        counts[name] = (counts[name] ?? 0) + 1;
      }
    }
    return counts;
  }, [tasks]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    apiClient
      .getChatAgents()
      .then((res) => {
        if (!cancelled) setBackends(res.backends);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const counts = runningCounts();
  const enabled = backends.filter((b) => b.available);
  const disabled = backends.filter((b) => !b.available);
  const totalRunning = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <PopoverPanel kind="agents" minWidth={280}>
      <PopoverTitle>
        Agents{totalRunning > 0 ? ` · ${totalRunning} running` : ''}
      </PopoverTitle>
      {enabled.map((b) => {
        const running = counts[b.name] ?? 0;
        return (
          <div
            key={b.name}
            className="flex items-center gap-2.5 rounded-md px-2.5 py-2"
          >
            <span
              aria-label={running > 0 ? 'running' : 'idle'}
              className={
                running > 0
                  ? 'size-[7px] shrink-0 rounded-full bg-[var(--kagan-rail-running)] shadow-[0_0_6px_var(--kagan-rail-running)]'
                  : 'size-[7px] shrink-0 rounded-full bg-[var(--muted-foreground)]'
              }
            />
            <span className="flex-1 font-code text-[11.5px] text-[var(--foreground)]">
              {b.name}
            </span>
            {running > 0 ? (
              <span className="rounded-md bg-[rgba(63,181,142,0.10)] px-1.5 py-px font-code text-[9.5px] text-[var(--kagan-rail-running)]">
                {running}
              </span>
            ) : (
              <span className="font-code text-[10.5px] text-[var(--muted-foreground)]">
                idle
              </span>
            )}
          </div>
        );
      })}
      {disabled.length > 0 ? (
        <>
          <hr className="my-1 border-t border-[var(--border)]" />
          {disabled.map((b) => (
            <div
              key={b.name}
              className="flex items-center gap-2.5 rounded-md px-2.5 py-2 opacity-50"
            >
              <span className="size-[7px] shrink-0 rounded-full bg-[var(--border)]" />
              <span className="flex-1 font-code text-[11.5px] text-[var(--muted-foreground)]">
                {b.name}
              </span>
              <span className="font-code text-[10px] text-[var(--muted-foreground)]">
                unavailable
              </span>
            </div>
          ))}
        </>
      ) : null}
      {backends.length === 0 ? (
        <p className="px-2.5 py-3 font-code text-[11px] text-[var(--muted-foreground)]">
          Loading…
        </p>
      ) : null}
    </PopoverPanel>
  );
}
