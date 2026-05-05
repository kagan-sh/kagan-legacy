import { Braces } from 'lucide-react';
import { cn } from '@/lib/utils';
import { StreamingStatus } from '@/components/chat/streaming-status';
import type { ToolRendererProps } from './index';

export function JsReplRenderer({ args, status, result, partialResult }: ToolRendererProps) {
  const code = typeof args?.code === 'string' ? args.code : null;
  const output = result ?? partialResult;

  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          'flex items-center gap-2 text-[11px]',
          status === 'failed' ? 'text-[var(--destructive)]' : 'text-[var(--muted-foreground)]',
        )}
      >
        <Braces className="size-3 shrink-0" />
        <span className="font-medium">JS REPL</span>
        {status === 'running' && (
          <StreamingStatus label="running" className="ml-auto" />
        )}
        {status === 'failed' && (
          <span className="ml-auto text-[var(--destructive)]">failed</span>
        )}
      </div>
      {code && (
        <pre className="overflow-x-auto rounded border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] p-2 font-code text-[10px] leading-relaxed text-[var(--foreground)]">
          {code}
        </pre>
      )}
      {output && (
        <pre
          className={cn(
            'overflow-x-auto rounded border p-2 font-code text-[10px] leading-relaxed',
            status === 'failed'
              ? 'border-[var(--destructive)]/20 bg-[var(--destructive)]/5 text-[var(--destructive)]'
              : 'border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] text-[var(--muted-foreground)]',
          )}
        >
          {output}
        </pre>
      )}
    </div>
  );
}
