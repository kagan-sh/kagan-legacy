import { FilePen } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ToolRendererProps } from './index';

export function EditRenderer({ args, status }: ToolRendererProps) {
  const path =
    typeof args?.path === 'string'
      ? args.path
      : typeof args?.file_path === 'string'
        ? args.file_path
        : null;

  return (
    <div className="flex items-center gap-2 text-[11px]">
      <FilePen
        className={cn(
          'size-3 shrink-0',
          status === 'failed' ? 'text-[var(--destructive)]' : 'text-[var(--muted-foreground)]',
        )}
      />
      <span className="min-w-0 flex-1 truncate font-medium text-[var(--muted-foreground)]">
        {path ?? 'Editing file'}
      </span>
      {status === 'running' && (
        <span className="shrink-0 text-[var(--kagan-thinking)]">editing</span>
      )}
      {status === 'failed' && (
        <span className="shrink-0 text-[var(--destructive)]">failed</span>
      )}
      {status === 'completed' && (
        <span className="shrink-0 text-[var(--kagan-rail-running)]">edited</span>
      )}
    </div>
  );
}
