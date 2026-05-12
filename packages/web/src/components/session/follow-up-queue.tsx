import { useState, useCallback, useRef, useEffect } from 'react';
import { Check, Pencil, Play, Square, Trash2, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';

/** A queued follow-up prompt. */
export interface QueuedPrompt {
  id: string;
  text: string;
}

interface FollowUpQueueProps {
  prompts: QueuedPrompt[];
  sending: boolean;
  agentRunning: boolean;
  onRemove: (id: string) => void;
  onEdit: (id: string, text: string) => void;
  onInterruptAndSend: (id: string) => void;
  className?: string;
}

export function FollowUpQueue({
  prompts,
  sending,
  agentRunning,
  onRemove,
  onEdit,
  onInterruptAndSend,
  className,
}: FollowUpQueueProps) {
  if (prompts.length === 0) return null;

  return (
    <div className={cn(' bg-[color:var(--surface-1)] shadow-[var(--soft-shadow)] p-4', className)}>
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[11px] font-medium uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
          Queued prompts ({prompts.length})
        </span>
      </div>
      <div className="space-y-2">
        {prompts.map((prompt) => (
          <QueueRow
            key={prompt.id}
            prompt={prompt}
            sending={sending}
            agentRunning={agentRunning}
            onRemove={onRemove}
            onEdit={onEdit}
            onInterruptAndSend={onInterruptAndSend}
          />
        ))}
      </div>
    </div>
  );
}

// ── Individual queue row ─────────────────────────────────────────────────────

function QueueRow({
  prompt,
  sending,
  agentRunning,
  onRemove,
  onEdit,
  onInterruptAndSend,
}: {
  prompt: QueuedPrompt;
  sending: boolean;
  agentRunning: boolean;
  onRemove: (id: string) => void;
  onEdit: (id: string, text: string) => void;
  onInterruptAndSend: (id: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(prompt.text);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const handleSave = useCallback(() => {
    const trimmed = draft.trim();
    if (trimmed && trimmed !== prompt.text) {
      onEdit(prompt.id, trimmed);
    }
    setEditing(false);
  }, [draft, prompt.id, prompt.text, onEdit]);

  const handleCancel = useCallback(() => {
    setDraft(prompt.text);
    setEditing(false);
  }, [prompt.text]);

  if (editing) {
    return (
      <div className=" border border-[var(--primary)]/40 bg-[var(--background)] p-2">
        <Textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSave(); }
            if (e.key === 'Escape') handleCancel();
          }}
          rows={2}
          className="mb-2 min-h-0 resize-none text-sm"
        />
        <div className="flex items-center gap-1">
          <Button size="icon-xs" variant="ghost" onClick={handleSave} aria-label="Save edit">
            <Check className="size-3.5 text-[var(--kagan-rail-running)]" />
          </Button>
          <Button size="icon-xs" variant="ghost" onClick={handleCancel} aria-label="Cancel edit">
            <X className="size-3.5 text-[var(--muted-foreground)]" />
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="group flex items-start gap-2 border border-[color:var(--border-subtle)] bg-[var(--background)] p-2">
      <p className="min-w-0 flex-1 text-sm text-[var(--foreground)] line-clamp-3">
        {prompt.text}
      </p>
      <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
        <Button
          size="icon-xs"
          variant="ghost"
          onClick={() => { setDraft(prompt.text); setEditing(true); }}
          disabled={sending}
          aria-label="Edit prompt"
          title="Edit"
        >
          <Pencil className="size-3.5" />
        </Button>
        <Button
          size="icon-xs"
          variant="ghost"
          onClick={() => onRemove(prompt.id)}
          disabled={sending}
          aria-label="Remove prompt"
          title="Remove"
        >
          <Trash2 className="size-3.5 text-[var(--destructive)]" />
        </Button>
        {agentRunning ? (
          <Button
            size="icon-xs"
            variant="ghost"
            onClick={() => onInterruptAndSend(prompt.id)}
            disabled={sending}
            aria-label="Interrupt agent and send this prompt"
            title="Interrupt & send"
          >
            <Square className="size-3.5 text-[var(--kagan-thinking)]" />
          </Button>
        ) : (
          <Button
            size="icon-xs"
            variant="ghost"
            onClick={() => onInterruptAndSend(prompt.id)}
            disabled={sending}
            aria-label="Send this prompt"
            title="Start with this prompt"
          >
            <Play className="size-3.5 text-[var(--kagan-rail-running)]" />
          </Button>
        )}
      </div>
    </div>
  );
}
