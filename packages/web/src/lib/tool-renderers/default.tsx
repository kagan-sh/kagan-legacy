import { Code } from 'lucide-react';
import { cn } from '@/lib/utils';
import { StreamingStatus } from '@/components/chat/streaming-status';
import type { ToolRendererProps } from './index';

export function DefaultRenderer({ name, args, status, result, partialResult }: ToolRendererProps) {
  const displayArgs = args ? JSON.stringify(args, null, 2) : null;
  const output = result ?? partialResult;

  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          'flex items-center gap-2 text-[11px]',
          status === 'failed' ? 'text-[var(--destructive)]' : 'text-[var(--muted-foreground)]',
        )}
      >
        <Code className="size-3 shrink-0" />
        <span className="font-medium">{name}</span>
        {status === 'running' && (
          <StreamingStatus label="running" />
        )}
        {status === 'failed' && (
          <span className="text-[var(--destructive)]">failed</span>
        )}
      </div>
      {displayArgs && (
        <pre className="overflow-x-auto rounded border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] p-2 font-code text-[10px] leading-relaxed text-[var(--foreground)]">
          {displayArgs}
        </pre>
      )}
      {output && (
        <pre className="overflow-x-auto rounded border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] p-2 font-code text-[10px] leading-relaxed text-[var(--muted-foreground)]">
          {output}
        </pre>
      )}
    </div>
  );
}
