import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Bot, BrainCircuit, ChevronRight } from 'lucide-react';
import { MarkdownContent } from '@/components/shared/markdown-content';
import { cn } from '@/lib/utils';
import type { ChatStreamEntry } from '@/lib/atoms/chat';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { StreamingGlyph } from '@/components/chat/streaming-glyph';

interface ChatStreamEntriesProps {
  entries: ChatStreamEntry[];
}

/**
 * Renders real-time streaming entries — text, thinking, tool calls, errors.
 * Uses flat-timeline layout consistent with ChatMessage.
 */
export function ChatStreamEntries({ entries }: ChatStreamEntriesProps) {
  if (entries.length === 0) return null;

  return (
    <>
      {entries.map((entry, i) => {
        const key = `stream-${i}-${entry.kind}`;
        switch (entry.kind) {
          case 'text':
            return <StreamTextBlock key={key} content={entry.content} />;
          case 'thought':
            return <StreamThoughtBlock key={key} content={entry.content} startedAt={entry.startedAt} />;
          case 'tool':
            return (
              <StreamToolCard
                key={key}
                id={entry.id}
                name={entry.name}
                status={entry.status}
                detail={entry.detail}
                args={entry.args}
                startedAt={entry.startedAt}
              />
            );
          case 'note':
            return <StreamNoteRow key={key} message={entry.message} />;
          case 'error':
            return <StreamErrorBlock key={key} message={entry.message} />;
        }
      })}
    </>
  );
}

// ── Agent text output ────────────────────────────────────────────────────────

function StreamTextBlock({ content }: { content: string }) {
  return (
    <div className="flex gap-3 py-3" data-testid="chat-stream-agent-text">
      <Avatar className="mt-0.5 size-6 shrink-0">
        <AvatarFallback className="bg-[var(--muted)]">
          <Bot className="size-3.5 text-[var(--muted-foreground)]" />
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="mb-1">
          <span className="text-[11px] font-semibold text-[var(--foreground)]">Agent</span>
        </div>
        <MarkdownContent
          content={content}
          className="text-[var(--foreground)] prose-headings:text-[var(--foreground)] prose-strong:text-[var(--foreground)] prose-code:text-[var(--primary)] prose-pre:bg-[var(--muted)] prose-pre:text-[var(--foreground)]"
        />
      </div>
    </div>
  );
}

// ── Thinking block ───────────────────────────────────────────────────────────

function StreamThoughtBlock({ content, startedAt }: { content: string; startedAt: number }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const id = setInterval(
      () => setElapsed(Math.round((Date.now() - startedAt) / 100) / 10),
      100,
    );
    return () => clearInterval(id);
  }, [startedAt]);
  const tokens = Math.round(content.length / 4);
  return (
    <div className="flex gap-3 py-3 opacity-70">
      <Avatar className="mt-0.5 size-6 shrink-0">
        <AvatarFallback className="bg-fuchsia-500/15">
          <BrainCircuit className="size-3.5 text-fuchsia-400" />
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="mb-1">
          <span className="text-[11px] font-semibold text-fuchsia-400">
            Thinking&nbsp;&nbsp;{elapsed}s&nbsp;·&nbsp;{tokens} tokens
          </span>
        </div>
        <MarkdownContent
          content={content}
          className="text-[var(--muted-foreground)] prose-headings:text-[var(--muted-foreground)] prose-strong:text-[var(--muted-foreground)] prose-code:text-fuchsia-400 prose-pre:bg-[var(--muted)] prose-pre:text-[var(--muted-foreground)]"
        />
      </div>
    </div>
  );
}

// ── Tool call card ────────────────────────────────────────────────────────────

/** Priority-ordered list of arg keys to surface as the key_arg hint. */
const KEY_ARG_CANDIDATES = ['path', 'file', 'command', 'query', 'pattern', 'task_id'] as const;

function extractKeyArg(args: Record<string, unknown> | null): string | null {
  if (!args) return null;
  for (const key of KEY_ARG_CANDIDATES) {
    const v = args[key];
    if (typeof v === 'string' && v.trim().length > 0) {
      const trimmed = v.trim();
      return trimmed.length > 40 ? `…${trimmed.slice(-38)}` : trimmed;
    }
  }
  // Fall back to first string-valued key
  for (const [, v] of Object.entries(args)) {
    if (typeof v === 'string' && v.trim().length > 0) {
      const trimmed = v.trim();
      return trimmed.length > 40 ? `…${trimmed.slice(-38)}` : trimmed;
    }
  }
  return null;
}

function formatElapsed(ms: number, status: 'running' | 'done' | 'failed'): string {
  if (status === 'running' && ms < 1000) return '';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function StreamToolCard({
  id: _id,
  name,
  status,
  detail,
  args,
  startedAt,
}: {
  id: string;
  name: string;
  status: 'running' | 'done' | 'failed';
  detail?: string;
  args: Record<string, unknown> | null;
  startedAt: number;
}) {
  const [expanded, setExpanded] = useState(false);
  const [elapsed, setElapsed] = useState(() => Date.now() - startedAt);
  // Show spinner only for the first 500ms to avoid jitter on instant tools
  const showSpinner = status === 'running' && elapsed < 500;
  // Ref so the interval closure always reads the latest startedAt
  const startedAtRef = useRef(startedAt);
  startedAtRef.current = startedAt;

  useEffect(() => {
    if (status !== 'running') {
      setElapsed(Date.now() - startedAtRef.current);
      return;
    }
    const id = setInterval(() => {
      setElapsed(Date.now() - startedAtRef.current);
    }, 1000);
    return () => clearInterval(id);
  }, [status]);

  const keyArg = extractKeyArg(args);
  const elapsedStr = formatElapsed(elapsed, status);
  const hasDetail = Boolean(detail);
  const headerLabel = keyArg ? `${name} (${keyArg})` : name;

  return (
    <div
      className={cn(
        'ml-9 my-1 bg-[color:var(--surface-1)] shadow-[var(--ambient-shadow)]',
        status === 'running' && 'border-l-2 border-[var(--kagan-thinking)]',
      )}
    >
      {/* Collapsed single-line header */}
      <div className="flex items-center gap-1.5 px-3 py-1.5 text-[11px]">
        {status === 'failed' ? (
          <span className="shrink-0 text-[var(--destructive)]" aria-label="Tool call failed">
            {'✗'}
          </span>
        ) : (
          <span
            className={cn(
              'shrink-0',
              status === 'running' ? 'text-[var(--kagan-thinking)]' : 'text-[var(--muted-foreground)]',
            )}
            aria-label={status === 'running' ? 'Tool call running' : 'Tool call completed'}
          >
            {showSpinner ? <StreamingGlyph className="text-[11px] leading-none" /> : '▸'}
          </span>
        )}
        <span
          className={cn(
            'min-w-0 flex-1 truncate font-medium',
            status === 'failed' ? 'text-[var(--destructive)]' : 'text-[var(--foreground)]',
          )}
        >
          {headerLabel}
        </span>
        {elapsedStr && (
          <span className="shrink-0 font-code text-[10px] text-[var(--muted-foreground)]">
            {elapsedStr}
          </span>
        )}
        {hasDetail && (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="ml-0.5 shrink-0 text-[var(--muted-foreground)] transition-colors hover:text-[var(--foreground)]"
            aria-label={expanded ? `Collapse ${name} details` : `Expand ${name} details`}
          >
            <ChevronRight
              className={cn('size-3 transition-transform duration-150', expanded && 'rotate-90')}
            />
          </button>
        )}
      </div>
      {/* Expandable detail panel */}
      {expanded && hasDetail && (
        <pre className="mx-3 mb-2 overflow-x-auto border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] p-2 font-code text-[10px] leading-relaxed text-[var(--muted-foreground)]">
          {detail}
        </pre>
      )}
    </div>
  );
}

// ── Error block ──────────────────────────────────────────────────────────────

function StreamErrorBlock({ message }: { message: string }) {
  return (
    <div className="ml-9 my-1 flex items-start gap-2 border border-[var(--destructive)]/20 bg-[var(--destructive)]/5 px-3 py-2 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[var(--destructive)]" />
      <p className="min-w-0 flex-1 text-[var(--destructive)]">{message}</p>
    </div>
  );
}

function StreamNoteRow({ message }: { message: string }) {
  return (
    <div className="ml-9 my-1 text-[11px] text-[var(--muted-foreground)]">{message}</div>
  );
}
