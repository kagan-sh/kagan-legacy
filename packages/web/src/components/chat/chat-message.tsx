import type { WireChatMessage } from '@/lib/api/types';
import { Bot, User } from 'lucide-react';
import { MarkdownContent } from '@/components/shared/markdown-content';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';

interface ChatMessageProps {
  message: WireChatMessage;
}

/**
 * Flat-timeline chat message — left-aligned, role-labeled.
 * Matches coding-assistant UX (Claude Code, OpenCode, Codex).
 * No bubble styling — clean, readable, scannable.
 */
export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user';

  return (
    <div className="flex gap-3 py-3" data-role={message.role}>
      <Avatar className="mt-0.5 size-6 shrink-0">
        <AvatarFallback className={isUser ? 'bg-[var(--primary)]/15' : 'bg-[var(--muted)]'}>
          {isUser ? (
            <User className="size-3.5 text-[var(--primary)]" />
          ) : (
            <Bot className="size-3.5 text-[var(--muted-foreground)]" />
          )}
        </AvatarFallback>
      </Avatar>
      <div className="min-w-0 flex-1">
        <div className="mb-1">
          <span className="text-[11px] font-semibold text-[var(--foreground)]">
            {isUser ? 'You' : 'Agent'}
          </span>
        </div>
        {isUser ? (
          <p className="text-sm leading-relaxed text-[var(--foreground)] whitespace-pre-wrap">{message.content}</p>
        ) : (
          <MarkdownContent
            content={message.content}
            className="text-[var(--foreground)] prose-headings:text-[var(--foreground)] prose-strong:text-[var(--foreground)] prose-code:text-[var(--primary)] prose-pre:bg-[var(--muted)] prose-pre:text-[var(--foreground)]"
          />
        )}
      </div>
    </div>
  );
}
