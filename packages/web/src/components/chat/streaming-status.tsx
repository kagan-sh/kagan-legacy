import { cn } from '@/lib/utils';
import { StreamingGlyph } from '@/components/chat/streaming-glyph';

interface StreamingStatusProps {
  label: string;
  className?: string;
}

export function StreamingStatus({ label, className }: StreamingStatusProps) {
  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1 font-code text-[10px] text-[var(--kagan-thinking)]', className)}>
      <StreamingGlyph className="text-[10px] leading-none" />
      <span>{label}</span>
    </span>
  );
}
