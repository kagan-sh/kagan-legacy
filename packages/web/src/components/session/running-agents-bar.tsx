/**
 * RunningAgentsBar — compact horizontal list of active worker/reviewer agents.
 *
 * Mirrors Claude Code's "background-agents picker": click a row to attach the
 * orchestrator overlay to that agent's event stream.
 *
 * Source: runningAgentsAtom (backed by GET /api/v1/agents/running + SSE).
 * Action: calls attachChatSessionAtom.
 *
 * Keyboard: arrow keys + Enter when the bar is focused; Tab moves focus out.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAtomValue, useSetAtom } from 'jotai';
import { runningAgentsAtom } from '@/lib/atoms/running-agents';
import { attachChatSessionAtom } from '@/lib/atoms/chat-attach';
import type { ActiveAgentRowResponse } from '@kagan/shared-api-client';
import { cn } from '@/lib/utils';

// ── Token formatter ──────────────────────────────────────────────────────────

function fmtTokens(n: number | null | undefined): string {
  if (!n) return '0';
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function fmtDuration(startedAt: string): string {
  const ms = Date.now() - new Date(startedAt).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h`;
}

function roleGlyph(role: string | null | undefined): string {
  if (role === 'reviewer') return 'R';
  return 'W';
}

// ── Agent row ────────────────────────────────────────────────────────────────

interface AgentRowProps {
  agent: ActiveAgentRowResponse;
  focused: boolean;
  onClick: () => void;
  buttonRef?: (el: HTMLButtonElement | null) => void;
}

function AgentRow({ agent, focused, onClick, buttonRef }: AgentRowProps) {
  const glyph = roleGlyph(agent.agent_role);
  const title = agent.task_title.length > 28
    ? `${agent.task_title.slice(0, 25).trimEnd()}…`
    : agent.task_title;
  const duration = fmtDuration(agent.started_at);
  const inTok = fmtTokens(agent.input_tokens);
  const outTok = fmtTokens(agent.output_tokens);

  return (
    <button
      ref={buttonRef}
      type="button"
      tabIndex={0}
      onClick={onClick}
      aria-label={`Attach to ${agent.agent_role ?? 'worker'} agent: ${agent.task_title}`}
      aria-current={focused ? 'true' : undefined}
      className={cn(
        'flex shrink-0 items-center gap-1.5 rounded-md border px-2 py-1 text-[11px] transition-colors',
        'border-[color:var(--border-subtle)] bg-[color:var(--surface-1)]',
        'hover:border-[color:var(--primary)] hover:text-[var(--foreground)]',
        'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--primary)]',
        focused && 'border-[color:var(--primary)] text-[var(--foreground)]',
        !focused && 'text-[var(--muted-foreground)]',
      )}
    >
      <span
        className={cn(
          'flex size-4 shrink-0 items-center justify-center rounded-full font-code text-[9px] font-bold',
          agent.agent_role === 'reviewer'
            ? 'bg-[var(--kagan-warning)]/20 text-[var(--kagan-warning)]'
            : 'bg-[var(--primary)]/20 text-[var(--primary)]',
        )}
        aria-hidden="true"
      >
        {glyph}
      </span>
      <span className="max-w-[140px] truncate">{title}</span>
      <span className="shrink-0 font-code text-[9px] text-[var(--muted-foreground)]">
        {duration} · ↑{inTok} ↓{outTok}
      </span>
    </button>
  );
}

// ── Bar ──────────────────────────────────────────────────────────────────────

interface RunningAgentsBarProps {
  /** Called when the user focuses the bar via ↓ from the chat input. */
  onFocusBar?: () => void;
  className?: string;
}

export function RunningAgentsBar({ onFocusBar: _onFocusBar, className }: RunningAgentsBarProps) {
  const { agents } = useAtomValue(runningAgentsAtom);
  const attach = useSetAtom(attachChatSessionAtom);
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Reset focus when agents list changes
  useEffect(() => {
    setFocusedIndex(-1);
  }, [agents.length]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (agents.length === 0) return;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        setFocusedIndex((i) => {
          const next = (i + 1) % agents.length;
          buttonRefs.current[next]?.focus();
          return next;
        });
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        setFocusedIndex((i) => {
          const prev = (i - 1 + agents.length) % agents.length;
          buttonRefs.current[prev]?.focus();
          return prev;
        });
      } else if (e.key === 'Enter' && focusedIndex >= 0) {
        e.preventDefault();
        const agent = agents[focusedIndex];
        if (agent) handleAttach(agent);
      }
    },
    [agents, focusedIndex], // eslint-disable-line react-hooks/exhaustive-deps
  );

  const handleAttach = useCallback(
    (agent: ActiveAgentRowResponse) => {
      attach({
        attachedSessionId: agent.session_id,
        taskTitle: agent.task_title,
        role: (agent.agent_role === 'reviewer' ? 'reviewer' : 'worker') as 'worker' | 'reviewer',
        startedAt: agent.started_at,
        inputTokens: agent.input_tokens ?? null,
        outputTokens: agent.output_tokens ?? null,
      });
    },
    [attach],
  );

  if (agents.length === 0) {
    return (
      <div
        className={cn(
          'flex items-center px-4 py-1.5 text-[11px] text-[var(--muted-foreground)]',
          className,
        )}
        aria-label="No agents running"
      >
        no agents running
      </div>
    );
  }

  return (
    <div
      role="list"
      aria-label="Running agents"
      className={cn('flex items-center gap-2 overflow-x-auto px-4 py-1.5', className)}
      onKeyDown={handleKeyDown}
    >
      {agents.map((agent, i) => (
        <div key={agent.session_id} role="listitem">
          <AgentRow
            agent={agent}
            focused={focusedIndex === i}
            onClick={() => handleAttach(agent)}
            buttonRef={(el) => {
              buttonRefs.current[i] = el;
            }}
          />
        </div>
      ))}
    </div>
  );
}
