/**
 * OrchestratorOverlay — the unified chat rail with three modes:
 *   - orchestrator: sends messages to the Kagan orchestrator chat session
 *   - worker:       streams events from an attached worker agent session
 *   - reviewer:     streams events from an attached reviewer agent session
 *
 * Keyboard:
 *   Cmd/Ctrl+K — toggle overlay (handled by app-layout)
 *   Esc (attached) — detach → orchestrator mode
 *   Esc (orchestrator) — close overlay
 *
 * Breadcrumb: "Orchestrator" or "Worker · running · 23s · ↑12k ↓3k"
 *
 * This component replaces the split ChatSidePanel + OrchestratorChatPanel for
 * the rail slot.  ChatSidePanel is kept for backward-compatibility and still
 * used in task-detail-page "Open chat" flow.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAtomValue, useSetAtom } from 'jotai';
import {
  ChevronLeft,
  Maximize2,
  MoreVertical,
  PanelBottom,
  PanelRight,
  RefreshCw,
  X,
} from 'lucide-react';
import { chatAttachAtom, detachChatSessionAtom } from '@/lib/atoms/chat-attach';
import { refreshRunningAgentsAtom } from '@/lib/atoms/running-agents';
import { sessionPickerOpenAtom, type RightRailMode } from '@/lib/atoms/ui';
import { apiClient } from '@/lib/api/client';
import type { SessionReplayEvent } from '@kagan/shared-api-client';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { OrchestratorChatPanel } from '@/components/session/orchestrator-chat-panel';
import { RunningAgentsBar } from '@/components/session/running-agents-bar';
import { EventStream } from '@/components/session/event-stream';
import { cn } from '@/lib/utils';
import { useIsMobile } from '@/lib/hooks/use-mobile';

// ── Token / duration helpers ─────────────────────────────────────────────────

function fmtTokens(n: number | null): string {
  if (!n) return '0';
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}

function fmtElapsed(startedAt: string): string {
  const s = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h`;
}

// ── Attached agent stream panel ───────────────────────────────────────────────

interface AgentStreamPanelProps {
  sessionId: string;
  taskTitle: string;
  role: 'worker' | 'reviewer';
  startedAt: string;
  inputTokens: number | null;
  outputTokens: number | null;
  layout: Exclude<RightRailMode, 'none'>;
  onSetLayout: (layout: Exclude<RightRailMode, 'none'>) => void;
  onDetach: () => void;
  onClose: () => void;
}

function AgentStreamPanel({
  sessionId,
  taskTitle,
  role,
  startedAt,
  inputTokens,
  outputTokens,
  layout,
  onSetLayout,
  onDetach,
  onClose,
}: AgentStreamPanelProps) {
  const isMobile = useIsMobile();
  const [events, setEvents] = useState<SessionReplayEvent[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [cursor, setCursor] = useState<string | null>(null);
  const [sseConnected, setSseConnected] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const [elapsed, setElapsed] = useState(() => fmtElapsed(startedAt));

  // Tick elapsed every second
  useEffect(() => {
    const id = setInterval(() => setElapsed(fmtElapsed(startedAt)), 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  // Load replay on mount
  useEffect(() => {
    let cancelled = false;
    setLoadingMore(true);
    apiClient
      .getSessionReplay(sessionId, { limit: 200, direction: 'backward' })
      .then((page) => {
        if (cancelled) return;
        setEvents(page.events);
        setHasMore(page.has_more ?? false);
        setCursor(page.next_cursor ?? null);
      })
      .catch(() => {
        if (!cancelled) setSseConnected(false);
      })
      .finally(() => {
        if (!cancelled) setLoadingMore(false);
      });
    return () => { cancelled = true; };
  }, [sessionId]);

  // SSE tail — listen on global kagan:session-event bus
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as
        | { event?: { session_id?: string; id?: string; type?: string; payload?: Record<string, unknown>; created_at?: string } }
        | undefined;
      const wireEvent = detail?.event;
      if (!wireEvent || wireEvent.session_id !== sessionId) return;
      setSseConnected(true);
      // Map WireEvent shape to SessionReplayEvent shape
      const replayEvent: SessionReplayEvent = {
        id: wireEvent.id ?? String(Date.now()),
        session_id: wireEvent.session_id,
        event_type: wireEvent.type ?? '',
        payload: wireEvent.payload ?? {},
        created_at: wireEvent.created_at ?? new Date().toISOString(),
      };
      setEvents((prev) => [...prev, replayEvent]);
    };
    window.addEventListener('kagan:session-event', handler);
    return () => window.removeEventListener('kagan:session-event', handler);
  }, [sessionId]);

  const loadEarlier = useCallback(async () => {
    if (!hasMore || !cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await apiClient.getSessionReplay(sessionId, {
        cursor,
        limit: 50,
        direction: 'backward',
      });
      setEvents((prev) => [...page.events, ...prev]);
      setHasMore(page.has_more ?? false);
      setCursor(page.next_cursor ?? null);
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, cursor, loadingMore, sessionId]);

  // Convert SessionReplayEvent → WireEvent shape for EventStream
  const wireEvents = events.map((e) => ({
    id: e.id,
    session_id: e.session_id ?? undefined,
    type: e.event_type,
    payload: e.payload,
    created_at: e.created_at,
  }));

  const breadcrumb = `${role === 'reviewer' ? 'Reviewer' : 'Worker'} · ${elapsed} · ↑${fmtTokens(inputTokens)} ↓${fmtTokens(outputTokens)}`;

  return (
    <aside
      data-chat-layout={layout}
      data-overlay-mode={role}
      className={cn(
        'flex h-full min-h-0 flex-col bg-[color:var(--surface-0)]',
        layout === 'chat-right' && 'border-l border-[color:var(--border-subtle)]',
        layout === 'chat-bottom' && 'border-t border-[color:var(--border-subtle)]',
        layout === 'chat-fullscreen' &&
          'w-full overflow-hidden border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/95 shadow-[var(--ambient-shadow)]',
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-3 py-2.5">
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label="Detach from agent, return to orchestrator"
          onClick={onDetach}
        >
          <ChevronLeft className="size-4" />
        </Button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-[var(--foreground)]">
            {breadcrumb}
          </p>
          <p className="truncate text-[10px] text-[var(--muted-foreground)]">{taskTitle}</p>
        </div>
        {!isMobile && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon-sm" aria-label="Chat layout options">
                <MoreVertical className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onSelect={() => onSetLayout('chat-right')}>
                <PanelRight className="size-4" />
                Dock right
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onSetLayout('chat-bottom')}>
                <PanelBottom className="size-4" />
                Dock bottom
              </DropdownMenuItem>
              <DropdownMenuItem onSelect={() => onSetLayout('chat-fullscreen')}>
                <Maximize2 className="size-4" />
                Fullscreen
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
        <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close overlay">
          <X className="size-4" />
        </Button>
      </div>

      {/* Reconnect banner */}
      {!sseConnected && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-2)] px-4 py-2 text-xs text-[var(--muted-foreground)]"
        >
          <RefreshCw className="size-3 animate-spin" aria-hidden="true" />
          Reconnecting…
        </div>
      )}

      {/* Event stream */}
      <EventStream
        events={wireEvents}
        isRunning={sseConnected}
        className="min-h-0 flex-1"
        hasMore={hasMore}
        loadingMore={loadingMore}
        onLoadEarlier={loadEarlier}
      />

      {/* Running agents bar */}
      <div className="border-t border-[color:var(--border-subtle)]">
        <RunningAgentsBar className="py-1" />
      </div>

      <div
        ref={abortRef as unknown as React.RefObject<HTMLDivElement>}
        className="sr-only"
        aria-hidden="true"
      />
    </aside>
  );
}

// ── Overlay ──────────────────────────────────────────────────────────────────

interface OrchestratorOverlayProps {
  /** Orchestrator chat session ID (used in orchestrator mode). */
  chatSessionId: string | null;
  layout: Exclude<RightRailMode, 'none'>;
  onSetLayout: (layout: Exclude<RightRailMode, 'none'>) => void;
  onClose: () => void;
}

export function OrchestratorOverlay({
  chatSessionId,
  layout,
  onSetLayout,
  onClose,
}: OrchestratorOverlayProps) {
  const attachTarget = useAtomValue(chatAttachAtom);
  const detach = useSetAtom(detachChatSessionAtom);
  const refreshAgents = useSetAtom(refreshRunningAgentsAtom);
  const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);

  // Refresh agents on mount and when layout changes
  useEffect(() => {
    void refreshAgents();
  }, [refreshAgents]);

  // Detach → orchestrator on Esc when attached
  useEffect(() => {
    if (!attachTarget) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
        detach();
      }
    };
    window.addEventListener('keydown', onKeyDown, { capture: true });
    return () => window.removeEventListener('keydown', onKeyDown, { capture: true });
  }, [attachTarget, detach]);

  // Attached mode — show agent stream panel
  if (attachTarget) {
    return (
      <AgentStreamPanel
        sessionId={attachTarget.attachedSessionId}
        taskTitle={attachTarget.taskTitle}
        role={attachTarget.role}
        startedAt={attachTarget.startedAt}
        inputTokens={attachTarget.inputTokens}
        outputTokens={attachTarget.outputTokens}
        layout={layout}
        onSetLayout={onSetLayout}
        onDetach={detach}
        onClose={onClose}
      />
    );
  }

  // Orchestrator mode — show OrchestratorChatPanel with RunningAgentsBar below input
  if (!chatSessionId) {
    return (
      <aside
        data-chat-layout={layout}
        data-overlay-mode="orchestrator"
        className={cn(
          'flex h-full min-h-0 flex-col bg-[color:var(--surface-0)]',
          layout === 'chat-right' && 'border-l border-[color:var(--border-subtle)]',
          layout === 'chat-bottom' && 'border-t border-[color:var(--border-subtle)]',
          layout === 'chat-fullscreen' &&
            'w-full overflow-hidden border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/95 shadow-[var(--ambient-shadow)]',
        )}
      >
        <div className="flex h-full items-center justify-center px-4 text-sm text-[var(--muted-foreground)]">
          <button
            type="button"
            className="underline decoration-dotted hover:text-[var(--foreground)]"
            onClick={() => setSessionPickerOpen(true)}
          >
            Select a session
          </button>
        </div>
        <div className="border-t border-[color:var(--border-subtle)]">
          <RunningAgentsBar />
        </div>
      </aside>
    );
  }

  return (
    <OrchestratorChatPanelWithAgentsBar
      sessionId={chatSessionId}
      layout={layout}
      onSetLayout={onSetLayout}
      onClose={onClose}
    />
  );
}

// ── OrchestratorChatPanel + RunningAgentsBar wrapper ─────────────────────────

interface OrchestratorChatPanelWithAgentsBarProps {
  sessionId: string;
  layout: Exclude<RightRailMode, 'none'>;
  onSetLayout: (layout: Exclude<RightRailMode, 'none'>) => void;
  onClose: () => void;
}

function OrchestratorChatPanelWithAgentsBar({
  sessionId,
  layout,
  onSetLayout,
  onClose,
}: OrchestratorChatPanelWithAgentsBarProps) {
  return (
    // Relative container so we can overlay the agents bar at the bottom of the
    // chat input without re-implementing the full OrchestratorChatPanel layout.
    <div
      data-overlay-mode="orchestrator"
      className="flex h-full min-h-0 flex-col"
    >
      <OrchestratorChatPanel
        sessionId={sessionId}
        layout={layout}
        onSetLayout={onSetLayout}
        onClose={onClose}
      />
      <RunningAgentsBar className="border-t border-[color:var(--border-subtle)]" />
    </div>
  );
}
