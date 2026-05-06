import { useEffect, useState } from 'react';
import { AlertTriangle, Bot, BrainCircuit } from 'lucide-react';
import { MarkdownContent } from '@/components/shared/markdown-content';
import { cn } from '@/lib/utils';
import type { ChatStreamEntry } from '@/lib/atoms/chat';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { StreamingGlyph } from '@/components/chat/streaming-glyph';
import { getToolRenderer } from '@/lib/tool-renderers';

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
            return <StreamToolCard key={key} id={entry.id} name={entry.name} status={entry.status} detail={entry.detail} />;
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
    <div className="flex gap-3 py-3">
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
          className="text-[var(--muted-foreground)] prose-headings:text-[var(--muted-foreground)] prose-strong:text-[var(--muted-foreground)] prose-code:text-fuchsia-400 pre:bg-[var(--muted)] prose-pre:text-[var(--muted-foreground)]"
        />
      </div>
    </div>
  );
}

// ── Tool call card — delegates to the registry ───────────────────────────────

function StreamToolCard({
  id,
  name,
  status,
  detail,
}: {
  id: string;
  name: string;
  status: 'running' | 'done';
  detail?: string;
}) {
  const rendererStatus = status === 'running' ? 'running' : 'completed';
  const Renderer = getToolRenderer(name);

  return (
    <div
      className={cn(
        'ml-9 my-1 bg-[color:var(--surface-1)] shadow-[var(--ambient-shadow)] px-3 py-2',
        status === 'running' && 'border-l-2 border-[var(--kagan-thinking)]',
      )}
    >
      <Renderer
        toolId={id}
        name={name}
        args={null}
        partialResult={detail ?? null}
        status={rendererStatus}
        result={status === 'done' ? (detail ?? null) : null}
      />
      {status === 'running' && (
        <StreamingGlyph className="mt-1 text-[11px] leading-none" />
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
