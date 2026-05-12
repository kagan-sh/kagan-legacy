/**
 * Agent CLI popover.
 *
 * Picks the local CLI program (claude-code, codex, gemini-cli, goose,
 * opencode, copilot, …) that runs the agent loop. We deliberately call
 * this "Agent CLI" — not "Model" — because in Kagan the user picks the
 * CLI program; the LLM is downstream of that choice.
 */
import { useEffect, useState } from 'react';
import { useAtom } from 'jotai';
import { currentAgentCliAtom } from '@/lib/atoms/shell';
import { apiClient } from '@/lib/api/client';
import { PopoverPanel, PopoverTitle, PopoverItem, useShellPopover } from '../popover';
import type { AgentBackendResponse } from '@kagan/shared-api-client';

export function AgentCliPopover() {
  const { isOpen, close } = useShellPopover('agent-cli', 'right');
  const [current, setCurrent] = useAtom(currentAgentCliAtom);
  const [backends, setBackends] = useState<AgentBackendResponse[]>([]);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    apiClient
      .getChatAgents()
      .then((res) => {
        if (cancelled) return;
        setBackends(res.backends.filter((b) => b.available));
        if (!current) setCurrent(res.default);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isOpen, current, setCurrent]);

  return (
    <PopoverPanel kind="agent-cli">
      <PopoverTitle>Agent CLI</PopoverTitle>
      {backends.map((b) => (
        <PopoverItem
          key={b.name}
          icon={current === b.name ? <span style={{ color: 'var(--primary)' }}>✓</span> : <span> </span>}
          label={b.name}
          desc={current === b.name ? 'Current' : undefined}
          active={current === b.name}
          onClick={() => {
            setCurrent(b.name);
            close();
          }}
        />
      ))}
    </PopoverPanel>
  );
}
