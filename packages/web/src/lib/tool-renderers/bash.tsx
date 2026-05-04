import { SquareTerminal } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolRendererProps } from './index';

export function BashRenderer({ args, status, result, partialResult }: ToolRendererProps) {
  const command = typeof args?.command === 'string' ? args.command : null;
  // partialResult is live output during streaming; result is the final output
  const output = result ?? partialResult;

  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          'flex items-center gap-2 text-[11px]',
          status === 'failed' ? 'text-[var(--destructive)]' : 'text-[var(--muted-foreground)]',
        )}
      >
        <SquareTerminal className="size-3 shrink-0" />
        <span className="font-medium">
          {command ? command : 'Running command…'}
        </span>
        {status === 'running' && (
          <span className="ml-auto text-[var(--kagan-thinking)]">running</span>
        )}
        {status === 'failed' && (
          <span className="ml-auto text-[var(--destructive)]">failed</span>
        )}
      </div>
      {output && (
        <pre
          className={cn(
            'overflow-x-auto rounded border p-2 font-code text-[10px] leading-relaxed',
            status === 'failed'
              ? 'border-[var(--destructive)]/20 bg-[var(--destructive)]/5 text-[var(--destructive)]'
              : 'border-[color:var(--border-subtle)] bg-[color:var(--surface-1)] text-[var(--foreground)]',
          )}
        >
          {output}
        </pre>
      )}
    </div>
  );
}
