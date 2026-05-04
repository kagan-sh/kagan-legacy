import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Bot, BrainCircuit, ChevronRight, User, Wrench } from 'lucide-react';
import { MarkdownContent } from '@/components/shared/markdown-content';
import type { WireEvent } from '@kagan/shared-api-client';
import { EVENT_TYPE } from '@kagan/shared-api-client';
import { parseUtc, parseUtcMs } from '@/lib/utils/time';
import { cn } from '@/lib/utils';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Panel } from '@/components/shared/workspace';
import { Button } from '@/components/ui/button';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { ChatOverlayEmptyState } from '@/components/session/chat-overlay-empty-state';
import { extractToolStatus, extractToolTitle } from '@/lib/api/event-rendering';

/** A user follow-up message displayed inline in the event stream. */
export interface UserFollowUp {
  text: string;
  timestamp: string;
}

interface EventStreamProps {
  events: WireEvent[];
  userFollowUps?: UserFollowUp[];
  isRunning?: boolean;
  className?: string;
  hasMore?: boolean;
  loadingMore?: boolean;
  onLoadEarlier?: () => void;
}

// ── Tool name / ID extraction (mirrors shared event rendering helpers) ───────

function acpPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const nested = payload.acp;
  return typeof nested === 'object' && nested !== null ? (nested as Record<string, unknown>) : {};
}

function extractToolId(payload: Record<string, unknown>, eventId: string): string {
  const acp = acpPayload(payload);
  return String(
    acp.toolCallId ?? acp.id ?? payload.tool_id ?? payload.id ?? eventId,
  );
}

/** Extract meaningful content from a tool call payload for display. */
function extractToolDetail(payload: Record<string, unknown>): Record<string, unknown> | null {
  const acp = acpPayload(payload);
  const detail: Record<string, unknown> = {};

  const input = acp.input ?? acp.rawInput ?? payload.args ?? payload.rawInput;
  if (input != null) detail.input = input;

  const output = acp.output ?? acp.rawOutput ?? payload.result ?? payload.rawOutput;
  if (output != null) detail.output = output;

  // If we extracted at least one meaningful field, use it; otherwise fall back to full payload
  // but strip internal metadata noise
  if (Object.keys(detail).length > 0) return detail;

  const { session_id: _s, created_at: _c, acp: _a, ...rest } = payload;
  return Object.keys(rest).length > 0 ? rest : null;
}

// ── Message coalescing (mirrors TUI StreamingOutput merge behaviour) ──────────

type StreamEntry =
  | { kind: 'message'; text: string; thought: boolean; time: string; ts: number }
  | { kind: 'tool'; id: string; title: string; status: string; payload: Record<string, unknown>; time: string; ts: number }
  | { kind: 'usage'; used: number; size: number; cost: number | null; currency: string | null; time: string; ts: number }
  | { kind: 'note'; label: string; detail?: string; time: string; ts: number }
  | { kind: 'user_follow_up'; text: string; time: string; ts: number };

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

function coalesceEvents(events: WireEvent[], userFollowUps?: UserFollowUp[]): StreamEntry[] {
  const entries: StreamEntry[] = [];

  for (const event of events) {
    const ts = parseUtcMs(event.created_at);
    const time = formatTime(parseUtc(event.created_at));
    const payload = event.payload ?? {};

    if (event.type === EVENT_TYPE.OUTPUT_CHUNK) {
      const text = (payload.text as string) ?? '';
      const thought = Boolean(payload.thought);
      if (!text) continue;

      const last = entries.at(-1);
      // Merge consecutive chunks of the same kind (like TUI merge=True)
      if (last?.kind === 'message' && last.thought === thought) {
        last.text += text;
        last.time = time;
        last.ts = ts;
      } else {
        entries.push({ kind: 'message', text, thought, time, ts });
      }
    } else if (event.type === EVENT_TYPE.TOOL_CALL_START || event.type === EVENT_TYPE.TOOL_CALL_UPDATE) {
      const toolId = extractToolId(payload, event.id);
      const title = extractToolTitle(payload);
      const defaultStatus = event.type === EVENT_TYPE.TOOL_CALL_START ? 'running' : 'done';
      const status = extractToolStatus(payload, defaultStatus);

      // Upsert — update existing tool entry or add new
      const existing = entries.find(
        (e): e is StreamEntry & { kind: 'tool' } => e.kind === 'tool' && e.id === toolId,
      );
      if (existing) {
        existing.status = status;
        existing.payload = payload;
        existing.time = time;
        existing.ts = ts;
      } else {
        entries.push({ kind: 'tool', id: toolId, title, status, payload, time, ts });
      }
    } else if (event.type === EVENT_TYPE.AGENT_COMPLETED) {
      entries.push({ kind: 'note', label: 'Agent completed', time, ts });
    } else if (event.type === EVENT_TYPE.AGENT_FAILED) {
      const detail = (payload.error as string) ?? (payload.details as string) ?? undefined;
      entries.push({ kind: 'note', label: 'Agent failed', detail, time, ts });
    } else if (event.type === EVENT_TYPE.TASK_STATUS_CHANGED) {
      const from = (payload.from as string) ?? '?';
      const to = (payload.to as string) ?? '?';
      entries.push({ kind: 'note', label: `Status: ${from} \u2192 ${to}`, time, ts });
    } else if (event.type === EVENT_TYPE.PLAN_UPDATE) {
      entries.push({ kind: 'note', label: 'Plan updated', time, ts });
    } else if (event.type === EVENT_TYPE.AUTO_REVIEW_STARTED) {
      entries.push({ kind: 'note', label: 'Auto-review started', time, ts });
    } else if (event.type === EVENT_TYPE.AGENT_STATUS) {
      const usage = payload.usage as Record<string, unknown> | undefined;
      if (usage && typeof usage.used === 'number' && typeof usage.size === 'number') {
        const existingIdx = entries.findIndex(e => e.kind === 'usage');
        const entry: StreamEntry = {
          kind: 'usage',
          used: usage.used as number,
          size: usage.size as number,
          cost: typeof usage.cost === 'number' ? usage.cost : null,
          currency: typeof usage.cost_currency === 'string' ? usage.cost_currency : null,
          time,
          ts,
        };
        if (existingIdx >= 0) {
          entries[existingIdx] = entry;
        } else {
          entries.push(entry);
        }
      } else {
        const text = (payload.text as string) ?? '';
        if (text) {
          entries.push({ kind: 'note', label: text, time, ts });
        }
      }
    } else {
      // Remaining event types (MERGE_COMPLETED, CRITERION_VERDICT, etc.) are not
      // rendered in the live stream — they are handled by other panels. The else
      // branch satisfies the exhaustiveness intent: every event visits exactly one
      // branch; new EVENT_TYPE values will fall here without breaking the renderer.
      void (event.type as string);
    }
  }

  // Interleave user follow-up messages by timestamp
  if (userFollowUps && userFollowUps.length > 0) {
    for (const followUp of userFollowUps) {
      const ts = Date.parse(followUp.timestamp);
      const time = formatTime(new Date(followUp.timestamp));
      entries.push({ kind: 'user_follow_up', text: followUp.text, time, ts });
    }
    entries.sort((a, b) => a.ts - b.ts);
  }

  return entries;
}

// ── Component ────────────────────────────────────────────────────────────────

const INITIAL_VISIBLE = 30;
const LOAD_MORE_STEP = 30;

export function EventStream({ events, userFollowUps, isRunning, className, hasMore, loadingMore, onLoadEarlier }: EventStreamProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const prevScrollHeight = useRef(0);
  const prevLoadingMore = useRef(loadingMore);
  const entries = useMemo(() => coalesceEvents(events, userFollowUps), [events, userFollowUps]);
  const [visibleCount, setVisibleCount] = useState(INITIAL_VISIBLE);

  // Auto-expand when new entries arrive (user is near bottom)
  const prevEntryCount = useRef(entries.length);
  useEffect(() => {
    if (entries.length > prevEntryCount.current) {
      const container = containerRef.current;
      const isNearBottom = container ? container.scrollHeight - container.scrollTop - container.clientHeight < 100 : true;
      if (isNearBottom) {
        setVisibleCount(entries.length);
      }
    }
    prevEntryCount.current = entries.length;
  }, [entries.length]);

  const visibleEntries = entries.length <= visibleCount
    ? entries
    : entries.slice(Math.max(0, entries.length - visibleCount));
  const hasHiddenEntries = entries.length > visibleCount;

  // Auto-scroll to bottom only when user is already near the bottom
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;
    if (isNearBottom) {
      container.scrollTop = container.scrollHeight;
    }
  }, [entries]);

  // After loading earlier events, restore scroll position so content doesn't jump
  useEffect(() => {
    if (prevLoadingMore.current && !loadingMore && containerRef.current) {
      const newScrollHeight = containerRef.current.scrollHeight;
      containerRef.current.scrollTop = newScrollHeight - prevScrollHeight.current;
    }
    prevLoadingMore.current = loadingMore;
  }, [loadingMore]);

  const handleLoadEarlier = useCallback(() => {
    if (containerRef.current) {
      prevScrollHeight.current = containerRef.current.scrollHeight;
    }
    onLoadEarlier?.();
  }, [onLoadEarlier]);

  const isEmpty = events.length === 0 && (!userFollowUps || userFollowUps.length === 0);

  if (isEmpty && !isRunning) {
    return <ChatOverlayEmptyState className={className} />;
  }

  if (isEmpty && isRunning) {
    return (
      <Panel className={cn('flex h-full min-h-0 flex-col overflow-hidden', className)}>
        <LiveIndicator />
        <div className="flex min-h-0 flex-1 flex-col items-center justify-center px-4 py-6 text-center">
          <p className="font-code text-sm font-medium text-[var(--foreground)]">Agent is starting up...</p>
          <p className="mt-1 font-code text-xs text-[var(--muted-foreground)]">Events will appear here as the agent works.</p>
        </div>
      </Panel>
    );
  }

  return (
    <Panel className={cn('flex h-full min-h-0 flex-col overflow-hidden', className)}>
      {isRunning && <LiveIndicator />}
      <div
        ref={containerRef}
        role="log"
        aria-live="polite"
        aria-relevant="additions text"
        aria-label="Agent event stream"
        className="min-h-0 flex-1 space-y-1 overflow-y-auto px-4 py-4"
      >
        {hasMore && onLoadEarlier ? (
          <button
            type="button"
            onClick={handleLoadEarlier}
            disabled={loadingMore}
            className="mb-3 flex w-full items-center justify-center gap-2 border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-3 py-2 font-code text-xs text-[var(--muted-foreground)] transition-colors hover:bg-[color:var(--muted)] hover:text-[var(--foreground)] disabled:opacity-50"
          >
            {loadingMore ? 'Loading...' : 'Load earlier events'}
          </button>
        ) : null}
        {hasHiddenEntries ? (
          <button
            type="button"
            onClick={() => setVisibleCount((c) => c + LOAD_MORE_STEP)}
            className="mb-3 flex w-full items-center justify-center gap-2 border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-3 py-2 font-code text-xs text-[var(--muted-foreground)] transition-colors hover:bg-[color:var(--muted)] hover:text-[var(--foreground)]"
          >
            Show {Math.min(LOAD_MORE_STEP, entries.length - visibleCount)} earlier messages
          </button>
        ) : null}
        {visibleEntries.map((entry, i) => {
          const key = `${i}-${entry.kind}`;
          if (entry.kind === 'message') return <AgentMessage key={key} text={entry.text} thought={entry.thought} time={entry.time} />;
          if (entry.kind === 'tool') return <ToolCallRow key={key} title={entry.title} status={entry.status} payload={entry.payload} time={entry.time} />;
          if (entry.kind === 'usage') return <UsageRow key={key} used={entry.used} size={entry.size} cost={entry.cost} currency={entry.currency} time={entry.time} />;
          if (entry.kind === 'user_follow_up') return <UserFollowUpMessage key={key} text={entry.text} time={entry.time} />;
          return <NoteRow key={key} label={entry.label} detail={entry.detail} time={entry.time} />;
        })}
      </div>
    </Panel>
  );
}

// ── LIVE indicator ───────────────────────────────────────────────────────────

function LiveIndicator() {
  return (
    <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-4 py-1.5">
      <span className="size-2 animate-pulse rounded-full bg-emerald-500" />
      <span className="font-code text-[10px] uppercase tracking-wider text-emerald-600">Live</span>
    </div>
  );
}

// ── Agent message (markdown bubble — same style as ChatMessage) ──────────────

function AgentMessage({ text, thought, time }: { text: string; thought: boolean; time: string }) {
  return (
    <div className="flex gap-3 py-2">
      <Avatar className="mt-0.5 size-6 shrink-0">
        <AvatarFallback className={thought ? 'bg-fuchsia-500/20' : 'bg-[var(--muted)]'}>
          {thought ? <BrainCircuit className="size-3.5 text-fuchsia-300" /> : <Bot className="size-3.5 text-[var(--muted-foreground)]" />}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex items-center gap-2">
          <span className="text-[11px] font-medium text-[var(--foreground)]">
            {thought ? 'Thinking' : 'Agent'}
          </span>
          <span className="font-code text-[10px] text-[var(--muted-foreground)]">{time}</span>
        </div>
        <MarkdownContent
          content={text}
          className=" bg-[var(--muted)] px-3 py-2 text-[var(--foreground)] prose-headings:text-[var(--foreground)] prose-strong:text-[var(--foreground)] prose-code:text-[var(--primary)] prose-pre:bg-[var(--background)] prose-pre:text-[var(--foreground)]"
        />
      </div>
    </div>
  );
}
// ── User follow-up (right-aligned bubble — mirrors TUI user messages) ────────
function UserFollowUpMessage({ text, time }: { text: string; time: string }) {
  return (
    <div className="flex gap-3 py-2 justify-end">
      <div className="min-w-0 max-w-[80%]">
        <div className="mb-0.5 flex items-center justify-end gap-2">
          <span className="font-code text-[10px] text-[var(--muted-foreground)]">{time}</span>
          <span className="text-[11px] font-medium text-[var(--foreground)]">You</span>
        </div>
        <div className=" bg-[var(--primary)] px-3 py-2 text-sm text-[var(--primary-foreground)]">
          {text}
        </div>
      </div>
      <Avatar className="mt-0.5 size-6 shrink-0">
        <AvatarFallback className="bg-[var(--primary)]/20">
          <User className="size-3.5 text-[var(--primary)]" />
        </AvatarFallback>
      </Avatar>
    </div>
  );
}
// ── Tool call (collapsible row — mirrors TUI ToolCallView) ───────────────────
function ToolCallRow({ title, status, payload, time }: { title: string; status: string; payload: Record<string, unknown>; time: string }) {
  const detail = extractToolDetail(payload);
  const hasDetail = detail !== null;
  return (
    <Collapsible disabled={!hasDetail}>
      <div className="flex items-center gap-2 bg-[color:var(--surface-1)] shadow-[var(--ambient-shadow)] px-3 py-1.5 text-[12px]">
        <Wrench className={cn('size-3.5 shrink-0', status === 'running' ? 'text-[var(--primary)] animate-pulse' : 'text-[var(--kagan-rail-running)]')} />
        <span className="min-w-0 flex-1 truncate font-medium text-[var(--foreground)]">{title}</span>
        <span className="font-code text-[10px] text-[var(--muted-foreground)]">{time}</span>
        {hasDetail ? (
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="icon-xs" className="size-5 " aria-label={`Toggle ${title} details`}>
              <ChevronRight className="size-3 transition-transform duration-150 [[data-state=open]_&]:rotate-90" />
            </Button>
          </CollapsibleTrigger>
        ) : null}
      </div>
      {hasDetail ? (
        <CollapsibleContent>
          <pre className="mx-3 mt-1 mb-2 overflow-x-auto border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] p-3 font-code text-[11px] leading-5 text-[var(--muted-foreground)]">
            {JSON.stringify(detail, null, 2)}
          </pre>
        </CollapsibleContent>
      ) : null}
    </Collapsible>
  );
}
// ── System note (status changes, plan updates, completions) ──────────────────
function NoteRow({ label, detail, time }: { label: string; detail?: string; time: string }) {
  const isError = label.toLowerCase().includes('failed');

  return (
    <div className="flex items-center gap-2 px-3 py-1 text-[11px]">
      <span className={cn('size-1.5 shrink-0 rounded-full', isError ? 'bg-[var(--destructive)]' : 'bg-[var(--muted-foreground)]')} />
      <span className={cn('font-medium', isError ? 'text-[var(--destructive)]' : 'text-[var(--muted-foreground)]')}>
        {label}
      </span>
      {detail ? (
        <span className="min-w-0 flex-1 truncate text-[var(--muted-foreground)]/70">{detail}</span>
      ) : null}
      <span className="ml-auto shrink-0 font-code text-[10px] text-[var(--muted-foreground)]">{time}</span>
    </div>
  );
}

function formatCost(cost: number, currency: string | null): string {
  const amount = cost.toFixed(4);
  if (!currency) return `$${amount}`;
  const c = currency.toUpperCase();
  if (currency === '$' || c === 'USD') return `$${amount}`;
  if (currency === '€' || c === 'EUR') return `€${amount}`;
  if (currency === '£' || c === 'GBP') return `£${amount}`;
  return `${currency} ${amount}`;
}

function UsageRow({ used, size, cost, currency, time }: { used: number; size: number; cost: number | null; currency: string | null; time: string }) {
  const pct = size > 0 ? (used / size) * 100 : 0;
  const pctClamped = Math.min(100, Math.max(0, pct));
  const barColor = pct > 80 ? 'bg-red-500' : pct > 60 ? 'bg-amber-500' : 'bg-emerald-500';
  const dotColor = pct > 80 ? 'bg-red-500' : pct > 60 ? 'bg-amber-500' : 'bg-emerald-500';
  const textColor = pct > 80 ? 'text-red-400' : pct > 60 ? 'text-amber-400' : 'text-[var(--muted-foreground)]';

  return (
    <div className={cn("flex items-center gap-2 px-3 py-1 text-[11px] font-code whitespace-nowrap", textColor)}>
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", dotColor)} />
      <span className="tabular-nums">ctx {used.toLocaleString()} / {size.toLocaleString()}</span>
      <span className="h-0.5 w-24 overflow-hidden rounded-full bg-[var(--muted)]">
        <span className={cn("block h-full", barColor)} style={{ width: `${pctClamped}%` }} />
      </span>
      <span className="tabular-nums">{pct.toFixed(1)}%</span>
      <span className="ml-auto flex items-center gap-3 tabular-nums">
        {cost != null ? <span>{formatCost(cost, currency)}</span> : null}
        <span className="shrink-0 text-[10px]">{time}</span>
      </span>
    </div>
  );
}
