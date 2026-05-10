import { useEffect, useState } from 'react';
import { useAtom } from 'jotai';
import { currentModelAtom } from '@/lib/atoms/shell';
import { apiClient } from '@/lib/api/client';
import { PopoverPanel, PopoverTitle, PopoverItem, PopoverSeparator, useShellPopover } from '../popover';
import type { AgentBackendResponse } from '@kagan/shared-api-client';

type ContextSize = 'high' | 'medium';

const CONTEXT_OPTIONS: Array<{ value: ContextSize; label: string; desc: string }> = [
  { value: 'high', label: 'High', desc: '200k tokens, long tasks' },
  { value: 'medium', label: 'Medium', desc: '50k tokens, standard' },
];

export function ModelPopover() {
  const { isOpen, close } = useShellPopover('model', 'right');
  const [currentModel, setCurrentModel] = useAtom(currentModelAtom);
  const [backends, setBackends] = useState<AgentBackendResponse[]>([]);
  const [contextSize, setContextSize] = useState<ContextSize>('high');

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    apiClient
      .getChatAgents()
      .then((res) => {
        if (!cancelled) {
          setBackends(res.backends.filter((b) => b.available));
          if (!currentModel) setCurrentModel(res.default);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isOpen, currentModel, setCurrentModel]);

  return (
    <PopoverPanel kind="model">
      <PopoverTitle>Model</PopoverTitle>
      {backends.map((b) => (
        <PopoverItem
          key={b.name}
          icon={
            currentModel === b.name ? (
              <span style={{ color: 'var(--primary)' }}>✓</span>
            ) : (
              <span> </span>
            )
          }
          label={b.name}
          desc={currentModel === b.name ? 'Current' : undefined}
          active={currentModel === b.name}
          onClick={() => {
            setCurrentModel(b.name);
            close();
          }}
        />
      ))}
      <PopoverSeparator />
      <PopoverTitle>Context</PopoverTitle>
      {CONTEXT_OPTIONS.map((opt) => (
        <PopoverItem
          key={opt.value}
          icon={
            contextSize === opt.value ? (
              <span style={{ color: 'var(--primary)' }}>✓</span>
            ) : (
              <span> </span>
            )
          }
          label={opt.label}
          desc={opt.desc}
          active={contextSize === opt.value}
          onClick={() => setContextSize(opt.value)}
        />
      ))}
    </PopoverPanel>
  );
}
