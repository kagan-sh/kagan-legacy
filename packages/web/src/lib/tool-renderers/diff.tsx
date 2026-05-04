import { FileDiff } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolRendererProps } from './index';

export function DiffRenderer({ args, status }: ToolRendererProps) {
  const path =
    typeof args?.path === 'string'
      ? args.path
      : typeof args?.file_path === 'string'
        ? args.file_path
        : null;

  return (
    <div className="space-y-1.5">
      <div
        className={cn(
          'flex items-center gap-2 text-[11px]',
          status === 'failed' ? 'text-[var(--destructive)]' : 'text-[var(--muted-foreground)]',
        )}
      >
        <FileDiff className="size-3 shrink-0" />
        <span className="min-w-0 flex-1 truncate font-medium">
          {path ?? 'Applying diff'}
        </span>
        {status === 'running' && (
          <span className="shrink-0 text-[var(--kagan-thinking)]">running</span>
        )}
        {status === 'failed' && (
          <span className="shrink-0 text-[var(--destructive)]">failed</span>
        )}
        {status === 'completed' && (
          <span className="shrink-0 text-[var(--kagan-rail-running)]">applied</span>
        )}
      </div>
    </div>
  );
}
