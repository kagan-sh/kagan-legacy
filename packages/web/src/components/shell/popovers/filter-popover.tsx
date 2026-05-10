import { useEffect, useState } from 'react';
import { useAtom } from 'jotai';
import { boardAgentFilterAtom } from '@/lib/atoms/board';
import { apiClient } from '@/lib/api/client';
import { PopoverPanel, PopoverTitle, PopoverItem, useShellPopover } from '../popover';
import type { AgentBackendResponse } from '@kagan/shared-api-client';

export function FilterPopover() {
  const { isOpen, close } = useShellPopover('filter', 'left');
  const [agentFilter, setAgentFilter] = useAtom(boardAgentFilterAtom);
  const [backends, setBackends] = useState<AgentBackendResponse[]>([]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    apiClient
      .getChatAgents()
      .then((res) => {
        if (!cancelled) setBackends(res.backends.filter((b) => b.available));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const select = (agent: string | null) => {
    setAgentFilter(agent);
    close();
  };

  return (
    <PopoverPanel kind="filter">
      <PopoverTitle>Filter by agent</PopoverTitle>
      <PopoverItem
        icon={<span style={{ color: 'var(--primary)' }}>✓</span>}
        label="All agents"
        desc="Show all tasks"
        active={agentFilter === null}
        onClick={() => select(null)}
      />
      {backends.map((b) => (
        <PopoverItem
          key={b.name}
          icon={
            <span className="font-code text-[9px] text-[var(--muted-foreground)]">
              {b.name.slice(0, 2).toUpperCase()}
            </span>
          }
          label={b.name}
          active={agentFilter === b.name}
          onClick={() => select(b.name)}
        />
      ))}
    </PopoverPanel>
  );
}
