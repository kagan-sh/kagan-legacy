import { useState, useCallback, useRef, useEffect, type KeyboardEvent, useMemo } from 'react';
import { Send, Plus, Paperclip, X } from 'lucide-react';
import { useAtomValue } from 'jotai';
import { isStreamingAtom } from '@/lib/atoms/chat';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { TypingIndicator } from '@/components/chat/typing-indicator';
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import {
  Command,
  CommandGroup,
  CommandItem,
  CommandList,
} from '@/components/ui/command';

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

export interface Attachment {
  id: string;
  type: string;
  name: string;
  content?: string;
  file?: File;
}

interface ChatInputBarProps {
  onSend: (text: string, attachments?: Attachment[]) => void;
  onSlashCommand?: (command: string) => void;
  onInterrupt?: (opts?: { pendingText: string | null }) => void;
  /** Override the streaming-atom check. When true, send is disabled. */
  disableSend?: boolean;
  placeholder?: string;
  className?: string;
  /** Pre-fill input text externally (e.g. after interrupt to edit last message). */
  externalPrefill?: string;
  /** Called after externalPrefill has been consumed. */
  onPrefillConsumed?: () => void;
}

export function ChatInputBar({
  onSend,
  onSlashCommand,
  onInterrupt,
  disableSend,
  placeholder,
  className,
  externalPrefill,
  onPrefillConsumed,
}: ChatInputBarProps) {
  const [text, setText] = useState('');
  const [showCommands, setShowCommands] = useState(false);
  const [selectedCommand, setSelectedCommand] = useState<string>('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const isStreaming = useAtomValue(isStreamingAtom);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const isBusy = disableSend ?? isStreaming;
  const canSend = (text.trim().length > 0 || attachments.length > 0) && !isBusy;

  useEffect(() => {
    if (externalPrefill != null) {
      setText(externalPrefill);
      onPrefillConsumed?.();
      inputRef.current?.focus();
    }
  }, [externalPrefill, onPrefillConsumed]);

  const filteredCommands = useMemo(() => {
    if (!text.startsWith('/')) return [];
    return SLASH_COMMANDS.filter((c) => c.command.startsWith(text.trim().toLowerCase()));
  }, [text]);

  const handleSend = useCallback(() => {
    if (!canSend) return;
    const trimmed = text.trim();
    if (trimmed.startsWith('/')) {
      onSlashCommand?.(trimmed);
    } else {
      onSend(trimmed, attachments.length > 0 ? attachments : undefined);
    }
    setText('');
    setAttachments([]);
    setShowCommands(false);
  }, [text, canSend, onSend, onSlashCommand, attachments]);

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
    // Ctrl+C always clears input — Esc interrupts the agent
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
      if (isBusy) {
        e.stopPropagation();
        const pending = text.trim();
        onInterrupt?.({ pendingText: pending || null });
        if (pending) setText('');
      }
      return;
    }

    if (showCommands && filteredCommands.length > 0) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        // Let Radix Command handle arrow navigation natively — do not preventDefault.
        return;
      }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault();
        // Use the currently highlighted command or fall back to first.
        const target = selectedCommand || filteredCommands[0]?.command || '';
        if (target) handleSelectCommand(target);
        return;
      }
      if (e.key === 'Escape') {
        setShowCommands(false);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    const newAttachments: Attachment[] = [];
    for (const file of Array.from(files)) {
      const type = file.type.startsWith('image/')
        ? 'image'
        : file.name.endsWith('.md') || file.name.endsWith('.markdown')
          ? 'markdown'
          : 'file';

      const attachment: Attachment = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        type,
        name: file.name,
        file,
      };

      // Read file content: base64 for images, text for code/markdown
      if (type === 'image') {
        try {
          const buf = await file.arrayBuffer();
          attachment.content = btoa(
            new Uint8Array(buf).reduce((s, b) => s + String.fromCharCode(b), ''),
          );
        } catch {
          // Fallback: keep file reference only
        }
      } else if (type === 'markdown' || file.type.startsWith('text/') || file.name.match(/\.(js|ts|tsx|jsx|py|rs|go|java|cpp|c|h|rb|php|json|yaml|yml|toml)$/)) {
        try {
          attachment.content = await file.text();
        } catch {
          // Fallback: keep file reference only
        }
      }

      newAttachments.push(attachment);
    }

    setAttachments((prev) => [...prev, ...newAttachments]);
    setAttachMenuOpen(false);
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => prev.filter((a) => a.id !== id));
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  return (
    <div className={cn('relative border-t border-[color:var(--border-subtle)] bg-[var(--card)] p-3', className)}>
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept="image/*,.md,.markdown,.txt,.js,.ts,.tsx,.jsx,.py,.rs,.go,.java,.cpp,.c,.h,.rb,.php,.json,.yaml,.yml,.toml"
        className="hidden"
        aria-label="Upload files"
        onChange={(e) => {
          handleFileSelect(e.target.files);
          e.target.value = ''; // Reset for re-selection
        }}
      />

      {/* Slash command autocomplete using shadcn Command */}
      {showCommands && filteredCommands.length > 0 && (
        <div className="absolute bottom-full left-3 right-3 mb-1 overflow-hidden border border-[color:var(--border-subtle)] bg-[var(--popover)] shadow-[var(--ambient-shadow)]">
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

      {/* Attachments preview */}
      {attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {attachments.map((att) => (
            <div
              key={att.id}
              className="inline-flex items-center gap-1.5 border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-2 py-1 text-xs"
            >
              <Paperclip className="size-3 text-[var(--primary)]" />
              <span className="max-w-24 truncate">{att.name}</span>
              <button
                onClick={() => removeAttachment(att.id)}
                disabled={isBusy}
                className="ml-1 p-0.5 hover:bg-[var(--accent)]"
                aria-label={`Remove ${att.name}`}
              >
                <X className="size-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-start gap-2">
        {/* Attachment menu popover */}
        <Popover open={attachMenuOpen} onOpenChange={setAttachMenuOpen}>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              size="icon"
              className="shrink-0 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
              aria-label="Add attachment"
            >
              <Plus className="size-4" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-56 p-1" align="start" side="top">
            <Button
              variant="ghost"
              className="h-auto w-full justify-start gap-3 px-3 py-2.5 text-left"
              onClick={openFilePicker}
            >
              <Paperclip className="size-4 shrink-0 text-[var(--primary)]" />
              <div className="flex flex-col items-start">
                <span className="text-sm font-medium">Add files or photos</span>
                <span className="text-xs text-[var(--muted-foreground)]">Images, docs, code files</span>
              </div>
            </Button>
          </PopoverContent>
        </Popover>

        <Textarea
          ref={inputRef}
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? 'Type a message or / for commands...'}
          rows={1}
          className="min-h-9 flex-1 resize-none py-2"
        />
        <Button
          size="icon"
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send message"
          className="shrink-0"
        >
          <Send className="size-4" />
        </Button>
      </div>

      {/* Footer bar — wave animation + interrupt hint; space is always reserved to prevent layout shift */}
      <div className={cn('mt-1.5 flex h-5 items-center gap-2.5 px-0.5', !isBusy && 'invisible')}>
        <TypingIndicator />
        <span className="text-[10px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
          <kbd className=" border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] px-1 py-0.5 font-code text-[9px]">esc</kbd>
          {' '}{text.trim() ? 'stop + send typed' : 'stop & edit last'}
        </span>
      </div>
    </div>
  );
}
