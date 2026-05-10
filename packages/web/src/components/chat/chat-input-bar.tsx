import {
  useState,
  useCallback,
  useRef,
  useEffect,
  useMemo,
  type KeyboardEvent,
  type ClipboardEvent,
} from 'react';
import { Send, Paperclip, Mic, ShieldCheck, MapPin, GitBranch, Cpu, X, Image } from 'lucide-react';
import { toast } from 'sonner';
import { useAtom, useAtomValue, useSetAtom } from 'jotai';
import { PENDING_QUEUE_MAX, type PendingMessage, type PendingMessageInput } from '@/lib/atoms/chat';
import {
  shellPopoverAtom,
  composerAccessAtom,
  composerLocalityAtom,
  composerBranchAtom,
  currentModelAtom,
  type ShellPopover,
} from '@/lib/atoms/shell';
import { cn } from '@/lib/utils';
import { TypingIndicator } from '@/components/chat/typing-indicator';
import {
  Command,
  CommandGroup,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { useChatInputHistory } from '@/lib/hooks/use-chat-input-history';
import { ATTACHMENT_MAX_COUNT, IMAGE_ATTACHMENT_MAX_BYTES } from '@/lib/chat-attachments';
import type { Attachment } from '@/lib/chat-attachments';

const SLASH_COMMANDS = [
  { command: '/help', description: 'Show available commands' },
  { command: '/clear', description: 'Clear the chat view' },
  { command: '/new', description: 'Start a new chat session' },
  { command: '/session', description: 'Show current session details' },
  { command: '/sessions', description: 'List chat sessions' },
  { command: '/agents', description: 'Switch agent backend' },
  { command: '/tool', description: 'Inspect tool calls' },
  { command: '/flow', description: 'Guided Plan → Execute → Orchestrate flow' },
  { command: '/exit', description: 'Exit the chat session' },
];

/** Access label shown on the Permissions chip. */
function accessLabel(access: 'full' | 'workspace' | 'readonly'): string {
  if (access === 'full') return 'Full access';
  if (access === 'workspace') return 'Workspace';
  return 'Read-only';
}

/** Locality label shown on the Locality chip. */
function localityLabel(locality: 'local' | 'remote'): string {
  return locality === 'local' ? 'Local' : 'Remote';
}

// ── Chip ─────────────────────────────────────────────────────────────────────

interface ChipProps {
  icon?: React.ReactNode;
  label: string;
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
  className?: string;
  'data-testid'?: string;
}

function Chip({ icon, label, onClick, className, 'data-testid': testId }: ChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-md border border-[var(--border)] bg-transparent px-2.5 py-1.5 font-code text-[11.5px] text-[var(--fg-muted)] transition-colors',
        'hover:bg-[var(--surface-2)] hover:border-[var(--panel-border-strong)]',
        className,
      )}
    >
      {icon ? <span className="size-3 shrink-0 [&>svg]:size-3">{icon}</span> : null}
      <span>{label}</span>
    </button>
  );
}

// ── Main props ────────────────────────────────────────────────────────────────

export interface ChatInputBarProps {
  onSend: (text: string, attachments?: Attachment[]) => void;
  onSlashCommand?: (command: string) => void;
  onInterrupt?: (opts?: { pendingText: string | null }) => void;
  disableSend?: boolean;
  placeholder?: string;
  className?: string;
  /** Active task branch. When null/undefined the Branch chip shows `main`. */
  activeBranch?: string | null;
  externalPrefill?: string;
  onPrefillConsumed?: () => void;
  projectId?: string;
  persistHistory?: boolean;
  isStreaming?: boolean;
  pendingQueue?: PendingMessage[];
  onEnqueue?: (input: string | PendingMessageInput) => boolean;
  onClearQueue?: () => void;
}

// ── Component ─────────────────────────────────────────────────────────────────

export function ChatInputBar({
  onSend,
  onSlashCommand,
  onInterrupt,
  disableSend,
  placeholder,
  className,
  activeBranch,
  externalPrefill,
  onPrefillConsumed,
  projectId,
  persistHistory = true,
  isStreaming = false,
  pendingQueue = [],
  onEnqueue,
  onClearQueue,
}: ChatInputBarProps) {
  const [text, setText] = useState('');
  const [showCommands, setShowCommands] = useState(false);
  const [selectedCommand, setSelectedCommand] = useState<string>('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isBusy = disableSend ?? false;
  const canSend = (text.trim().length > 0 || attachments.length > 0) && !isBusy;

  // ── Atoms ──────────────────────────────────────────────────────────────────

  const [access] = useAtom(composerAccessAtom);
  const locality = useAtomValue(composerLocalityAtom);
  const model = useAtomValue(currentModelAtom);
  const selectedBranch = useAtomValue(composerBranchAtom);
  const setPopover = useSetAtom(shellPopoverAtom);

  // ── History ────────────────────────────────────────────────────────────────

  const history = useChatInputHistory(projectId, persistHistory);

  // ── Auto-grow textarea ─────────────────────────────────────────────────────

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [text]);

  // ── External prefill ───────────────────────────────────────────────────────

  useEffect(() => {
    if (externalPrefill != null) {
      setText(externalPrefill);
      onPrefillConsumed?.();
      history.reset();
      inputRef.current?.focus();
    }
  }, [externalPrefill, onPrefillConsumed]);

  const filteredCommands = useMemo(() => {
    if (!text.startsWith('/')) return [];
    return SLASH_COMMANDS.filter((c) => c.command.startsWith(text.trim().toLowerCase()));
  }, [text]);

  // ── Send ───────────────────────────────────────────────────────────────────

  const doSend = useCallback(
    (txt: string, atts: Attachment[]) => {
      const trimmed = txt.trim();
      if (trimmed.startsWith('/')) {
        onSlashCommand?.(trimmed);
      } else {
        onSend(trimmed, atts.length > 0 ? atts : undefined);
      }
      if (trimmed.length > 0) history.push(trimmed);
      history.reset();
      setText('');
      setAttachments([]);
      setShowCommands(false);
    },
    [onSend, onSlashCommand],
  );

  const handleSend = useCallback(() => {
    if (!canSend) return;
    if (isStreaming && onEnqueue) {
      const ok = onEnqueue({
        text: text.trim(),
        ...(attachments.length > 0 ? { attachments } : {}),
      });
      if (!ok) {
        toast.error(`Queue full — max ${PENDING_QUEUE_MAX} messages`);
        return;
      }
      if (text.trim().length > 0) history.push(text.trim());
      history.reset();
      setText('');
      setAttachments([]);
      setShowCommands(false);
      return;
    }
    doSend(text, attachments);
  }, [text, canSend, isStreaming, onEnqueue, doSend, attachments]);

  const handleSelectCommand = (command: string) => {
    setText(command + ' ');
    setShowCommands(false);
    setSelectedCommand('');
    inputRef.current?.focus();
  };

  const handleChange = (value: string) => {
    setText(value);
    const open = value.startsWith('/') && value.length > 0 && !value.includes(' ');
    setShowCommands(open);
    if (open) setSelectedCommand('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.ctrlKey && !e.metaKey && e.key.toLowerCase() === 'c') {
      e.preventDefault();
      if (text.length > 0 || attachments.length > 0) {
        setText('');
        setAttachments([]);
        setShowCommands(false);
      }
      return;
    }

    if (e.key === 'Escape') {
      e.preventDefault();
      if (pendingQueue.length > 0) onClearQueue?.();
      if (isStreaming) {
        e.stopPropagation();
        const pending = text.trim();
        onInterrupt?.({ pendingText: pending || null });
        if (pending) setText('');
      }
      return;
    }

    if (!showCommands || filteredCommands.length === 0) {
      if (e.key === 'ArrowUp') {
        const entry = history.navigateUp(text);
        if (entry !== null) { e.preventDefault(); setText(entry); }
        return;
      }
      if (e.key === 'ArrowDown') {
        const entry = history.navigateDown();
        if (entry !== null) { e.preventDefault(); setText(entry); }
        return;
      }
    }

    if (showCommands && filteredCommands.length > 0) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') return;
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault();
        const target = selectedCommand || filteredCommands[0]?.command || '';
        if (target) handleSelectCommand(target);
        return;
      }
      if (e.key === 'Escape') { setShowCommands(false); return; }
    }

    if (e.key === 'Enter' && (e.metaKey || !e.shiftKey)) {
      e.preventDefault();
      handleSend();
    }
  };

  // ── File handling ─────────────────────────────────────────────────────────

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const available = ATTACHMENT_MAX_COUNT - attachments.length;
    if (available <= 0) { toast.error(`Max ${ATTACHMENT_MAX_COUNT} attachments per message`); return; }

    const newAttachments: Attachment[] = [];
    for (const file of Array.from(files).slice(0, available)) {
      const isImage = file.type.startsWith('image/');
      const type: Attachment['type'] = isImage
        ? 'image'
        : file.name.endsWith('.md') || file.name.endsWith('.markdown')
          ? 'markdown'
          : 'file';

      const attachment: Attachment = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        type,
        name: file.name,
        file,
        ...(isImage ? { mimeType: file.type } : {}),
      };

      if (type === 'image') {
        if (file.size > IMAGE_ATTACHMENT_MAX_BYTES) {
          toast.error(`Image too large — max ${IMAGE_ATTACHMENT_MAX_BYTES / (1024 * 1024)} MB`);
          continue;
        }
        try {
          const buf = await file.arrayBuffer();
          attachment.content = btoa(
            new Uint8Array(buf).reduce((s, b) => s + String.fromCharCode(b), ''),
          );
        } catch { /* keep file ref only */ }
      } else if (
        type === 'markdown' ||
        file.type.startsWith('text/') ||
        file.name.match(/\.(js|ts|tsx|jsx|py|rs|go|java|cpp|c|h|rb|php|json|yaml|yml|toml)$/)
      ) {
        try { attachment.content = await file.text(); } catch { /* keep file ref only */ }
      }

      newAttachments.push(attachment);
    }
    setAttachments((prev) => [...prev, ...newAttachments]);
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const handlePaste = useCallback(
    async (e: ClipboardEvent<HTMLTextAreaElement>) => {
      const items = Array.from(e.clipboardData.items);
      const imageItems = items.filter((item) => item.kind === 'file' && item.type.startsWith('image/'));
      if (imageItems.length === 0) return;

      const remaining = ATTACHMENT_MAX_COUNT - attachments.length;
      if (remaining <= 0) { toast.error(`Max ${ATTACHMENT_MAX_COUNT} attachments per message`); return; }

      const newAttachments: Attachment[] = [];
      for (const item of imageItems.slice(0, remaining)) {
        const file = item.getAsFile();
        if (!file) continue;
        if (file.size > IMAGE_ATTACHMENT_MAX_BYTES) {
          toast.error(`Image too large — max ${IMAGE_ATTACHMENT_MAX_BYTES / (1024 * 1024)} MB`);
          continue;
        }
        const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
        const name = file.name || `pasted-image-${id}.${file.type.split('/')[1] ?? 'png'}`;
        try {
          const buf = await file.arrayBuffer();
          const content = btoa(new Uint8Array(buf).reduce((s, b) => s + String.fromCharCode(b), ''));
          newAttachments.push({ id, type: 'image', name, mimeType: file.type, content, file });
        } catch { toast.error(`Failed to read pasted image: ${name}`); }
      }
      if (newAttachments.length > 0) setAttachments((prev) => [...prev, ...newAttachments]);
    },
    [attachments],
  );

  // ── Chip popover helpers ───────────────────────────────────────────────────

  const openPopover = (kind: ShellPopover) => (e: React.MouseEvent) => {
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    setPopover({
      kind,
      anchor: { x: rect.left, y: rect.top, align: 'left' },
    });
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  // composerBranchAtom overrides activeBranch when the user has picked explicitly.
  const branch = selectedBranch ?? activeBranch ?? 'main';

  return (
    <div className={cn('border-t border-[var(--border)] bg-[var(--bg)] px-8 py-3.5', className)}>
      <div className="relative mx-auto max-w-[760px]">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,.md,.markdown,.txt,.js,.ts,.tsx,.jsx,.py,.rs,.go,.java,.cpp,.c,.h,.rb,.php,.json,.yaml,.yml,.toml"
          className="hidden"
          aria-label="Upload files"
          onChange={(e) => { void handleFileSelect(e.target.files); e.target.value = ''; }}
        />

        {/* Slash command autocomplete */}
        {showCommands && filteredCommands.length > 0 && (
          <div className="absolute bottom-full left-0 right-0 mb-2 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface-1)] shadow-lg">
            <Command
              className="bg-transparent"
              value={selectedCommand}
              onValueChange={setSelectedCommand}
            >
              <CommandList className="max-h-60">
                <CommandGroup heading="Commands">
                  {filteredCommands.map((cmd) => (
                    <CommandItem
                      key={cmd.command}
                      value={cmd.command}
                      onSelect={() => handleSelectCommand(cmd.command)}
                      className="cursor-pointer"
                    >
                      <code className="mr-2 text-xs text-[var(--primary)]">{cmd.command}</code>
                      <span className="text-xs text-[var(--muted-foreground)]">{cmd.description}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              </CommandList>
            </Command>
          </div>
        )}

        {/* Composer box */}
        <div
          className={cn(
            'rounded-[10px] border border-[var(--border)] bg-[var(--surface-1)] transition-[border-color,box-shadow]',
            'focus-within:border-[var(--primary)] focus-within:shadow-[0_0_0_3px_var(--focus-ring)]',
          )}
        >
          {/* Attachment previews */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
              {attachments.map((att) => (
                <div
                  key={att.id}
                  className="inline-flex items-center gap-1.5 rounded border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 text-xs text-[var(--fg-muted)]"
                >
                  {att.type === 'image' ? (
                    att.file ? (
                      <img src={URL.createObjectURL(att.file)} alt={att.name} className="size-4 rounded object-cover" />
                    ) : (
                      <Image className="size-3 text-[var(--primary)]" />
                    )
                  ) : (
                    <Paperclip className="size-3 text-[var(--primary)]" />
                  )}
                  <span className="max-w-24 truncate">{att.name}</span>
                  <button
                    type="button"
                    onClick={() => removeAttachment(att.id)}
                    className="ml-0.5 p-px hover:text-[var(--foreground)]"
                    aria-label={`Remove ${att.name}`}
                  >
                    <X className="size-2.5" />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Textarea */}
          <textarea
            ref={inputRef}
            data-testid="chat-composer-input"
            value={text}
            onChange={(e) => handleChange(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder={placeholder ?? 'Type a message or / for commands…'}
            rows={1}
            className="block w-full resize-none bg-transparent px-4 pt-3.5 pb-1.5 text-[14px] leading-[1.55] text-[var(--fg)] placeholder:text-[var(--fg-dim)] outline-none"
            style={{ minHeight: '60px', maxHeight: '240px' }}
          />

          {/* Chip bar */}
          <div className="flex items-center gap-2 px-2.5 pb-2.5 pt-2 flex-wrap">
            {/* Attach — stub, TODO: wire to file-upload flow */}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              aria-label="Add attachment"
              data-testid="composer-attach-btn"
              className="grid size-[30px] shrink-0 place-items-center rounded-md border border-[var(--border)] bg-transparent text-[var(--fg-muted)] transition-colors hover:border-[var(--panel-border-strong)] hover:bg-[var(--surface-2)] hover:text-[var(--fg)]"
            >
              <Paperclip className="size-3.5" strokeWidth={1.8} />
            </button>

            {/* Permissions chip */}
            <Chip
              icon={<ShieldCheck strokeWidth={1.8} />}
              label={accessLabel(access)}
              onClick={openPopover('permissions')}
              data-testid="composer-permissions-chip"
              className="text-[var(--rail-review)] border-[rgba(194,124,78,0.22)] bg-[rgba(194,124,78,0.08)] hover:bg-[rgba(194,124,78,0.14)]"
            />

            {/* Locality chip */}
            <Chip
              icon={<MapPin strokeWidth={1.8} />}
              label={localityLabel(locality)}
              onClick={openPopover('locality')}
              data-testid="composer-locality-chip"
            />

            {/* Branch chip */}
            <Chip
              icon={<GitBranch strokeWidth={1.8} />}
              label={branch}
              onClick={openPopover('branch')}
              data-testid="composer-branch-chip"
            />

            {/* Model chip */}
            <Chip
              icon={<Cpu strokeWidth={1.8} />}
              label={model ?? 'Model'}
              onClick={openPopover('model')}
              data-testid="composer-model-chip"
            />

            <div className="flex-1" />

            {/* Pending queue badge */}
            {pendingQueue.length > 0 && (
              <div className="flex items-center gap-1">
                <span className="inline-flex items-center rounded border border-[var(--border)] bg-[var(--surface-2)] px-2 py-1 font-code text-[10px] text-[var(--fg-muted)]">
                  {pendingQueue.length} queued
                </span>
                <button
                  type="button"
                  onClick={() => onClearQueue?.()}
                  aria-label="Clear queue"
                  className="grid size-6 place-items-center rounded text-[var(--muted-foreground)] hover:text-[var(--destructive)]"
                >
                  <X className="size-3" />
                </button>
              </div>
            )}

            {/* Voice — placeholder */}
            <button
              type="button"
              onClick={() => toast.info('Voice not available')}
              aria-label="Voice input"
              data-testid="composer-voice-btn"
              className="grid size-[30px] shrink-0 place-items-center rounded-md border border-[var(--border)] bg-transparent text-[var(--fg-muted)] transition-colors hover:border-[var(--panel-border-strong)] hover:bg-[var(--surface-2)] hover:text-[var(--fg)]"
            >
              <Mic className="size-3.5" strokeWidth={1.8} />
            </button>

            {/* Send */}
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              aria-label="Send message"
              data-testid="composer-send-btn"
              className={cn(
                'grid size-8 shrink-0 place-items-center rounded-[7px] border-0 transition-[filter,background]',
                canSend
                  ? 'cursor-pointer bg-[var(--primary)] text-[#0b0a09] shadow-[0_0_18px_-4px_rgba(212,168,75,0.5)] hover:brightness-110'
                  : 'cursor-not-allowed bg-[var(--surface-3)] text-[var(--fg-dim)]',
              )}
            >
              <Send className="size-3.5" strokeWidth={1.8} />
            </button>
          </div>
        </div>

        {/* Composer foot — kbd hints */}
        <div className="mt-2 flex items-center gap-3 font-code text-[11.5px] tracking-[0.02em] text-[var(--fg-muted)]">
          <span>
            <kbd className="rounded border border-[var(--border)] bg-[var(--surface-2)] px-1 py-px text-[10px] text-[var(--primary-soft)]">⌘↵</kbd>
            {' '}send
          </span>
          <span>
            <kbd className="rounded border border-[var(--border)] bg-[var(--surface-2)] px-1 py-px text-[10px] text-[var(--primary-soft)]">⇧↵</kbd>
            {' '}newline
          </span>
          <span>
            <kbd className="rounded border border-[var(--border)] bg-[var(--surface-2)] px-1 py-px text-[10px] text-[var(--primary-soft)]">Esc</kbd>
            {' '}{isStreaming ? 'stop' : 'blur'}
          </span>
          <div className="flex-1" />
          {isStreaming ? (
            <span className="flex items-center gap-1.5">
              <TypingIndicator />
              <span className="text-[10px] uppercase tracking-[0.16em]">streaming</span>
            </span>
          ) : (
            <span className="text-[var(--fg-dim)]">{model ? `model · ${model}` : 'model'}</span>
          )}
        </div>
      </div>
    </div>
  );
}
