import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, Bot, BrainCircuit, Check, ChevronRight, Loader2 } from 'lucide-react';
import { MarkdownContent } from '@/components/shared/markdown-content';
import { cn } from '@/lib/utils';
import type { ChatStreamEntry } from '@/lib/atoms/chat';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { StreamingGlyph } from '@/components/chat/streaming-glyph';

interface ChatStreamEntriesProps {
  entries: ChatStreamEntry[];
  showReasoning?: boolean;
}

/**
 * Renders real-time streaming entries — text, thinking, tool calls, errors.
 * Uses flat-timeline layout consistent with ChatMessage.
 *
 * `showReasoning` (default false) controls whether thought blocks render
 * expanded with full content.  When false only a collapsed one-liner is shown.
 */
export function ChatStreamEntries({ entries, showReasoning = false }: ChatStreamEntriesProps) {
  if (entries.length === 0) return null;

  return (
    <>
      {entries.map((entry, i) => {
        const key = `stream-${i}-${entry.kind}`;
        switch (entry.kind) {
          case 'text':
            return <StreamTextBlock key={key} content={entry.content} />;
          case 'thought':
            return (
              <StreamThoughtBlock
                key={key}
                content={entry.content}
                startedAt={entry.startedAt}
                showReasoning={showReasoning}
              />
            );
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
          case 'worked':
            return (
              <WorkedAccordion
                key={key}
                label={entry.label}
                steps={entry.steps}
                done={entry.done}
                startedAt={entry.startedAt}
              />
            );
          case 'files':
            return <FilesChangedBlock key={key} items={entry.items} />;
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

function StreamThoughtBlock({
  content,
  startedAt,
  showReasoning,
}: {
  content: string;
  startedAt: number;
  showReasoning: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    const id = setInterval(
      () => setElapsed(Math.round((Date.now() - startedAt) / 100) / 10),
      100,
    );
    return () => clearInterval(id);
  }, [startedAt]);
  const tokens = Math.round(content.length / 4);
  const isExpanded = showReasoning || expanded;

  return (
    <div className="flex gap-3 py-3 opacity-70" data-testid="chat-stream-thought">
      <Avatar className="mt-0.5 size-6 shrink-0">
        <AvatarFallback className="bg-fuchsia-500/15">
          <BrainCircuit className="size-3.5 text-fuchsia-400" />
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2">
          <span className="text-[11px] font-semibold text-fuchsia-400">
            thinking…&nbsp;{elapsed}s&nbsp;·&nbsp;{tokens}&nbsp;tok
          </span>
          {/* Per-block toggle — only shown when global showReasoning is off */}
          {!showReasoning && content.trim().length > 0 && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="text-[10px] text-fuchsia-400/60 hover:text-fuchsia-400 transition-colors"
              aria-label={expanded ? 'Collapse reasoning' : 'Expand reasoning'}
              aria-expanded={expanded}
            >
              <ChevronRight
                className={cn('size-3 transition-transform duration-150', expanded && 'rotate-90')}
              />
            </button>
          )}
        </div>
        {isExpanded && content.trim().length > 0 && (
          <MarkdownContent
            content={content}
            className="text-[var(--muted-foreground)] prose-headings:text-[var(--muted-foreground)] prose-strong:text-[var(--muted-foreground)] prose-code:text-fuchsia-400 prose-pre:bg-[var(--muted)] prose-pre:text-[var(--muted-foreground)]"
          />
        )}
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

// ── Worked accordion ─────────────────────────────────────────────────────────

/**
 * Collapsible accordion that groups a batch of tool steps under a
 * "Worked for Ns" header.  Mirrors the `.worked` / `.worked-steps` design.
 *
 * - Closed by default; click toggles `data-open`.
 * - Live state (done=false) shows a spinning icon; done state shows a check.
 * - Spin animation is suppressed by the `.worked-icon-live` media rule when
 *   `prefers-reduced-motion: reduce` is active.
 */
function WorkedAccordion({
  label,
  steps,
  done,
  startedAt: _startedAt,
}: {
  label: string;
  steps: string[];
  done: boolean;
  startedAt: number;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="flex flex-col" data-testid="worked-accordion">
      {/* Header pill */}
      <button
        type="button"
        data-open={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'inline-flex w-fit cursor-pointer select-none items-center gap-2',
          'rounded-md border border-[var(--border)] bg-[var(--surface-1)]',
          'px-2.5 py-1 font-code text-[12px] text-[var(--muted-foreground)]',
          'transition-[border-color] duration-[var(--motion-fast)]',
          'hover:border-[var(--panel-border-strong)]',
        )}
        aria-expanded={open}
        aria-label={open ? 'Collapse tool steps' : 'Expand tool steps'}
      >
        {/* Status icon: spinning Loader2 when live, check when done */}
        {done ? (
          <Check
            className="size-3 shrink-0 text-[var(--kagan-rail-running)]"
            aria-hidden="true"
            data-testid="worked-icon-done"
          />
        ) : (
          <Loader2
            className="worked-icon-live size-3 shrink-0 text-[var(--primary)]"
            aria-hidden="true"
            data-testid="worked-icon-live"
          />
        )}
        <span>{label}</span>
        <ChevronRight
          className={cn(
            'size-3 shrink-0 text-[var(--muted-foreground)] transition-transform duration-[var(--motion-fast)]',
            open && 'rotate-90',
          )}
          aria-hidden="true"
        />
      </button>

      {/* Steps list */}
      <div
        data-open={open}
        className={cn(
          'ml-1.5 border-l-2 border-[var(--border)] pl-3.5',
          'flex flex-col gap-1 overflow-y-auto font-code text-[11.5px] leading-relaxed text-[var(--muted-foreground)]',
          'transition-[max-height,opacity,padding] duration-[var(--motion-base)]',
          open ? 'max-h-[280px] pt-3 pb-1 opacity-100' : 'max-h-0 overflow-hidden border-transparent py-0 opacity-0',
        )}
        aria-hidden={!open}
        data-testid="worked-steps"
      >
        {steps.map((step, idx) => {
          // Steps are formatted as "<timestamp>  <action>" — split on double-space
          const splitIdx = step.indexOf('  ');
          const ts = splitIdx >= 0 ? step.slice(0, splitIdx) : '';
          const action = splitIdx >= 0 ? step.slice(splitIdx + 2) : step;
          return (
            <div key={idx} className="flex gap-2">
              {ts && (
                <span className="shrink-0 text-[var(--muted-foreground)]/60">{ts}</span>
              )}
              <span className="text-[var(--primary)]/80">{action}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Files changed block ───────────────────────────────────────────────────────

/**
 * Renders a list of filenames changed during the agent's last action.
 * Matches `.msg-assistant ul/li/file` from the design:
 *   - `›` glyph in `var(--primary)` before each item
 *   - monospace filename with dashed amber underline
 *   - click navigates to diff viewer (no-op when no worktree)
 */
function FilesChangedBlock({ items }: { items: string[] }) {
  if (items.length === 0) return null;

  return (
    <div
      className="flex flex-col gap-3 pl-0"
      data-testid="files-changed-block"
      aria-label="Changed files"
    >
      <span className="font-code text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
        Changed
      </span>
      <ul className="flex list-none flex-col gap-1.5 p-0">
        {items.map((filename) => (
          <li
            key={filename}
            className="flex items-center gap-2.5 text-[14px] text-[var(--foreground)]/80"
          >
            <span
              className="font-code font-bold text-[var(--primary)]"
              aria-hidden="true"
            >
              ›
            </span>
            {/* Using <a> as the design specifies; href="#" is a no-op placeholder
                when no worktree diff viewer is active. The caller can swap this
                to a router link once diff navigation is wired. */}
            <a
              href="#"
              className={cn(
                'font-code text-[13px] text-[var(--primary)]/80',
                'border-b border-dashed border-[rgba(240,200,104,0.3)]',
                'hover:border-[var(--primary)] hover:text-[var(--primary)]',
                'transition-[color,border-color] duration-[var(--motion-fast)]',
                'cursor-pointer no-underline',
              )}
              data-testid="file-link"
              onClick={(e) => e.preventDefault()}
              aria-label={`View diff for ${filename}`}
            >
              {filename}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
