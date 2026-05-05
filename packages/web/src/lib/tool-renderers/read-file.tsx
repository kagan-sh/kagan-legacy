import { FileText } from 'lucide-react';
import { cn } from '@/lib/utils';
import { StreamingStatus } from '@/components/chat/streaming-status';
import type { ToolRendererProps } from './index';

export function ReadFileRenderer({ args, status }: ToolRendererProps) {
  const path =
    typeof args?.path === 'string'
      ? args.path
      : typeof args?.file_path === 'string'
        ? args.file_path
        : null;

  return (
    <div className="flex items-center gap-2 text-[11px]">
      <FileText
        className={cn(
          'size-3 shrink-0',
          status === 'failed' ? 'text-[var(--destructive)]' : 'text-[var(--muted-foreground)]',
        )}
      />
      <span className="min-w-0 flex-1 truncate font-medium text-[var(--muted-foreground)]">
        {path ?? 'Reading file'}
      </span>
      {status === 'running' && (
        <StreamingStatus label="reading" />
      )}
      {status === 'failed' && (
        <span className="shrink-0 text-[var(--destructive)]">failed</span>
      )}
      {status === 'completed' && (
        <span className="shrink-0 text-[var(--kagan-rail-running)]">read</span>
      )}
    </div>
  );
}
